"""
Headless batch-translate engine for the Supervertaler for Trados large-file
offload feature (see Supervertaler-for-Trados#42 / Workbench#230).

Trados Studio 2024 is a 32-bit process and crashes on very large jobs. The
plugin hands the batch to this 64-bit Workbench, which translates it WITHOUT a
GUI (pure Python - no Qt, no window) and returns a TMX the plugin re-imports.

Contract (invoked by the plugin):

    supervertaler --batch <job.json> --out <result.tmx> [--result <result.json>]

`--batch` is detected in Supervertaler.main() BEFORE any QApplication is created,
so this path never touches the GUI.

job.json (schemaVersion 1):
    {
      "schemaVersion": 1,
      "sourceLang": "en-US",
      "targetLang": "nl-NL",
      "provider": "openai",            # llm_clients provider id
      "model": "gpt-5.4-mini",
      "baseUrl": null,                  # optional (Ollama / custom OpenAI)
      "apiKey": "sk-...",               # optional; else settingsPath is read
      "settingsPath": "C:/.../settings.json",  # optional fallback for the key
      "httpProxy": null,                # optional
      "systemPrompt": "...",            # resolved by the plugin (prompt + glossary)
      "batchSize": 20,
      "maxTokens": 16384,               # optional
      "segments": [ { "id": 1, "source": "..." }, ... ]
    }

result.json:
    { "ok": true, "translated": N, "failed": M, "errors": [...] }

This module deliberately reuses modules.llm_clients.LLMClient (the real provider
calls). The thin batch-prompt assembly + numbered-response parsing mirror
PreTranslationWorker._translate_batch_with_llm; a later refactor should unify the
two behind one helper (tracked in the offload design doc).
"""

import argparse
import json
import os
import re
import sys
import traceback


def _resolve_api_key(job):
    """Key from the job, else from a referenced settings.json's api_keys section."""
    key = (job.get("apiKey") or "").strip()
    if key:
        return key
    provider = (job.get("provider") or "").strip()
    settings_path = job.get("settingsPath")
    if settings_path and os.path.isfile(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
            api_keys = settings.get("api_keys", settings) or {}
            k = api_keys.get(provider)
            if not k and provider == "gemini":
                k = api_keys.get("google")
            if k:
                return k.strip()
        except Exception:
            pass
    return ""


def build_batch_prompt(batch, source_lang, target_lang, system_prompt):
    """Numbered batch user-prompt. Mirrors PreTranslationWorker._translate_batch_with_llm."""
    parts = []
    if not system_prompt:
        parts.append(f"Translate the following text segments from {source_lang} to {target_lang}.")
    parts.append(f"**SEGMENTS TO TRANSLATE ({len(batch)} segments):**")
    parts.append("\n⚠️ CRITICAL INSTRUCTIONS:")
    parts.append("1. You must provide EXACTLY one translation per segment")
    parts.append(f"2. You MUST translate ALL {len(batch)} segments")
    parts.append("3. Format: Each translation MUST start with its segment number, a period, then the translation")
    parts.append("4. Line breaks: If the source segment contains line breaks, preserve them in your translation.")
    parts.append("   The number label (e.g. '40.') appears only ONCE at the start; continuation lines have no number.")
    next_rule = 5
    has_inline_tags = any(re.search(r'</?\d+/?>', (seg.get("source") or "")) for seg in batch)
    if has_inline_tags:
        parts.append(
            f"{next_rule}. Inline tags: some segments contain numbered tags like "
            "<1>…</1> (paired) or <2/> (standalone). Keep EVERY tag, with the same "
            "numbers, exactly as written - angle brackets, digits, no spaces. A paired "
            "tag MUST wrap the translated word(s) it wrapped in the source; NEVER output "
            "an empty pair like <1></1> with the text left outside it. Tags may be "
            "reordered to fit natural target-language word order.")
        next_rule += 1
    parts.append(f"{next_rule}. NO explanations, NO commentary, ONLY the numbered translations\n")
    parts.append("**SEGMENTS TO TRANSLATE:**\n")
    for seg in batch:
        parts.append(f"{seg['id']}. {seg['source']}")
    parts.append("\n**YOUR TRANSLATIONS (numbered list):**")
    parts.append("Begin your translations now:")
    return "\n".join(parts)


def parse_batch_response(result, batch):
    """Map a numbered response back to segment ids. Mirrors the worker's parser."""
    out = {}
    if not result:
        return out
    current_id = None
    for line in result.split("\n"):
        m = re.match(r'^(\d+)\.\s*(.*)', line)
        if m:
            current_id = int(m.group(1))
            out[current_id] = m.group(2)
        elif current_id is not None:
            out[current_id] += "\n" + line
    return out


def run_job(job, out_tmx, result_path=None, self_test=False, log=print):
    """Translate every segment in `job` and write a TMX. Returns a result dict."""
    segments = job.get("segments") or []
    source_lang = job.get("sourceLang") or "en"
    target_lang = job.get("targetLang") or "nl"
    system_prompt = job.get("systemPrompt") or None
    batch_size = int(job.get("batchSize") or 20)
    if batch_size <= 0:
        batch_size = 20

    errors = []
    client = None
    if not self_test:
        try:
            from modules.llm_clients import LLMClient
        except Exception as e:
            return {"ok": False, "translated": 0, "failed": len(segments),
                    "errors": ["could not import LLMClient: " + str(e)]}
        api_key = _resolve_api_key(job)
        if not api_key and (job.get("provider") not in ("ollama",)):
            return {"ok": False, "translated": 0, "failed": len(segments),
                    "errors": ["no API key for provider '" + str(job.get("provider")) + "' "
                               "(pass apiKey or settingsPath in the job)"]}
        client = LLMClient(
            api_key=api_key,
            provider=job.get("provider") or "openai",
            model=job.get("model"),
            max_tokens=int(job.get("maxTokens") or 16384),
            base_url=job.get("baseUrl"),
            http_proxy=job.get("httpProxy"),
        )

    id_to_target = {}
    total = len(segments)
    total_batches = (total + batch_size - 1) // batch_size
    for bi in range(total_batches):
        batch = segments[bi * batch_size: (bi + 1) * batch_size]
        prompt = build_batch_prompt(batch, source_lang, target_lang, system_prompt)
        try:
            if self_test:
                # Offline plumbing check: echo each source as its own translation.
                response = "\n".join(f"{seg['id']}. {seg['source']}" for seg in batch)
            else:
                response = client.translate(
                    text=prompt,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    custom_prompt=prompt,
                    system_prompt=system_prompt,
                    enable_prompt_caching=True,
                )
            parsed = parse_batch_response(response, batch)
            got = 0
            for seg in batch:
                t = parsed.get(seg["id"])
                if t is not None and t.strip():
                    id_to_target[seg["id"]] = t
                    got += 1
            log(f"[batch {bi + 1}/{total_batches}] {got}/{len(batch)} translated")
        except Exception as e:
            errors.append(f"batch {bi + 1}: {e}")
            log(f"[batch {bi + 1}/{total_batches}] ERROR: {e}")

    # Build TMX from the source/target pairs we got.
    src_list, tgt_list = [], []
    for seg in segments:
        t = id_to_target.get(seg["id"])
        if t is not None and t.strip():
            src_list.append(seg["source"])
            tgt_list.append(t)

    try:
        from modules.tmx_generator import TMXGenerator
        gen = TMXGenerator(log_callback=lambda *_: None)
        tree = gen.generate_tmx(src_list, tgt_list, source_lang, target_lang)
        os.makedirs(os.path.dirname(os.path.abspath(out_tmx)), exist_ok=True)
        gen.save_tmx(tree, out_tmx)
    except Exception as e:
        errors.append("TMX write failed: " + str(e))

    translated = len(tgt_list)
    res = {
        "ok": translated > 0 and not errors,
        "translated": translated,
        "failed": total - translated,
        "tmx": os.path.abspath(out_tmx),
        "errors": errors,
    }
    if result_path:
        try:
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    return res


def cli_main(argv):
    """Entry point reached from Supervertaler.main() when --batch is present."""
    parser = argparse.ArgumentParser(prog="supervertaler --batch", add_help=True)
    parser.add_argument("--batch", required=True, metavar="job.json",
                        help="path to the job description JSON")
    parser.add_argument("--out", required=True, metavar="result.tmx",
                        help="path to write the result TMX")
    parser.add_argument("--result", metavar="result.json",
                        help="path to write the result summary JSON (counts/errors)")
    parser.add_argument("--self-test", action="store_true",
                        help="offline plumbing check: echo sources, no LLM call")
    args, _ = parser.parse_known_args(argv)

    try:
        with open(args.batch, "r", encoding="utf-8") as f:
            job = json.load(f)
    except Exception as e:
        print("ERROR: could not read job file: " + str(e))
        return 2

    try:
        res = run_job(job, args.out, result_path=args.result, self_test=args.self_test)
    except Exception:
        print("ERROR: batch run crashed:\n" + traceback.format_exc())
        return 1

    print("RESULT " + json.dumps(res, ensure_ascii=False))
    return 0 if res.get("ok") else 1
