"""
═══════════════════════════════════════════════════════════════════════════════
Image Extractor Module for Supervertaler
═══════════════════════════════════════════════════════════════════════════════

Purpose:
    Extract images from DOCX files and save them as sequentially numbered PNG
    files in **document order** (Fig. 1.png is the first image that appears
    when you scroll the document top-to-bottom).

Features:
    - Extract all body-content images from DOCX in document order
    - Skip header/footer images (logos, banners — not figures)
    - Skip duplicates (same image referenced twice in body → one PNG)
    - Save as PNG with sequential naming (Fig. 1.png, Fig. 2.png, …)

v1.10.189 fix:
    The previous implementation walked ``word/media/`` in ZIP namelist order,
    which on most systems is **lexical**: image1, image10, image11, …, image19,
    image2, image3, …, image9. With 19 figures this produced ``Fig. 7.png``
    containing the document's 15th image instead of FIG. 7. The extractor now
    parses ``word/document.xml`` for ``r:embed`` / ``r:link`` references in the
    order they appear in the body, maps each rId through
    ``word/_rels/document.xml.rels`` to its media file, and emits the figures
    in that order. Header/footer references (e.g. company logos in
    ``word/header*.xml``) are excluded — they're not figures and were
    previously polluting the figure numbering.

Author: Supervertaler Development Team
Created: 2025-11-17
Last Modified: 2026-05-26 (v1.10.189)

═══════════════════════════════════════════════════════════════════════════════
"""

import os
import re
from pathlib import Path
from typing import List, Tuple, Optional
from zipfile import ZipFile
from io import BytesIO
from PIL import Image


# Match any image-bearing relationship attribute in document XML.
# - r:embed = embedded DrawingML image (modern Word)
# - r:link  = linked DrawingML image (less common)
# Both reference an entry in word/_rels/document.xml.rels by rId.
_EMBED_RE = re.compile(r'r:(?:embed|link)="([^"]+)"')

# Parse Relationship entries from a rels XML file.
_REL_RE = re.compile(r'<Relationship\s+[^>]*Id="([^"]+)"[^>]*Target="([^"]+)"')


def _get_body_images_in_document_order(zip_ref: ZipFile) -> List[str]:
    """Return the list of media-file paths (inside the ZIP) referenced from
    word/document.xml, in the order they appear in the document body.

    Duplicates are collapsed — if the same image is referenced twice in the
    body, only its first occurrence makes the list. Header / footer
    references are excluded by construction (we only walk document.xml,
    not header*.xml / footer*.xml).

    Returns ``[]`` on any parse error so the caller can fall back to the
    naïve ZIP-namelist scan.
    """
    try:
        # 1. Build rId → media-file mapping from the document's rels file.
        rels_bytes = zip_ref.read('word/_rels/document.xml.rels')
        rels_text = rels_bytes.decode('utf-8', errors='replace')
        rel_map = {}
        for rid, target in _REL_RE.findall(rels_text):
            # Targets are relative to word/ — normalise to full ZIP path.
            # Examples seen in real DOCX: "media/image3.png", "../media/image3.png".
            t = target.lstrip('./')
            if t.startswith('media/'):
                rel_map[rid] = 'word/' + t

        # 2. Walk document.xml in order, collect distinct media paths.
        doc_bytes = zip_ref.read('word/document.xml')
        doc_text = doc_bytes.decode('utf-8', errors='replace')

        ordered = []
        seen = set()
        for rid in _EMBED_RE.findall(doc_text):
            media = rel_map.get(rid)
            if not media:
                continue
            if media in seen:
                continue
            seen.add(media)
            ordered.append(media)
        return ordered
    except KeyError:
        # word/document.xml or its rels file is missing — atypical DOCX.
        return []
    except Exception:
        return []


def _process_image_bytes(img_bytes: bytes) -> Optional[Image.Image]:
    """Decode raw image bytes and return a PIL Image converted to RGB so
    it's safe to save as PNG. Returns None if decoding fails."""
    try:
        img = Image.open(BytesIO(img_bytes))
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        return img
    except Exception:
        return None


class ImageExtractor:
    """Extract images from DOCX files and save as PNG, in document order."""

    def __init__(self):
        self.supported_formats = ['.docx']

    def extract_images_from_docx(self, docx_path: str, output_dir: str,
                                 prefix: str = "Fig.") -> Tuple[int, List[str]]:
        """Extract all body-content images from a single DOCX in document
        order.

        Args:
            docx_path: Path to the DOCX file
            output_dir: Directory where images will be saved
            prefix: Prefix for output filenames (default: "Fig.")

        Returns:
            (number of images extracted, list of output file paths)
        """
        if not os.path.exists(docx_path):
            raise FileNotFoundError(f"DOCX file not found: {docx_path}")
        if not docx_path.lower().endswith('.docx'):
            raise ValueError("File must be a DOCX document")

        os.makedirs(output_dir, exist_ok=True)

        extracted_files: List[str] = []
        try:
            with ZipFile(docx_path, 'r') as zip_ref:
                ordered_media = _get_body_images_in_document_order(zip_ref)

                # Fallback: if document-order parsing produced nothing
                # (corrupt rels file, exotic DOCX flavour) we don't want
                # to silently extract zero figures, so fall back to the
                # legacy scan. Sort with a natural-key so image1, image2,
                # …, image10 doesn't go lexical.
                if not ordered_media:
                    raw = [f for f in zip_ref.namelist()
                           if f.startswith('word/media/')]
                    ordered_media = sorted(raw, key=_natural_key)

                for fig_num, img_file in enumerate(ordered_media, start=1):
                    try:
                        img_bytes = zip_ref.read(img_file)
                    except KeyError:
                        continue
                    img = _process_image_bytes(img_bytes)
                    if img is None:
                        print(f"Warning: Could not process image {img_file}")
                        continue

                    output_filename = f"{prefix} {fig_num}.png"
                    output_path = os.path.join(output_dir, output_filename)
                    img.save(output_path, 'PNG', optimize=True)
                    extracted_files.append(output_path)
        except Exception as e:
            raise Exception(f"Error extracting images: {e}")

        return len(extracted_files), extracted_files

    def extract_from_multiple_docx(self, docx_paths: List[str], output_dir: str,
                                   prefix: str = "Fig.") -> Tuple[int, List[str]]:
        """Extract images from multiple DOCX files with continuous
        numbering across them (Fig. 1 .. Fig. N where N spans all files).

        Each file's images are emitted in its own document order; the
        global counter advances across file boundaries.
        """
        os.makedirs(output_dir, exist_ok=True)

        all_extracted_files: List[str] = []
        current_number = 1

        for docx_path in docx_paths:
            try:
                with ZipFile(docx_path, 'r') as zip_ref:
                    ordered_media = _get_body_images_in_document_order(zip_ref)
                    if not ordered_media:
                        raw = [f for f in zip_ref.namelist()
                               if f.startswith('word/media/')]
                        ordered_media = sorted(raw, key=_natural_key)

                    for img_file in ordered_media:
                        try:
                            img_bytes = zip_ref.read(img_file)
                        except KeyError:
                            continue
                        img = _process_image_bytes(img_bytes)
                        if img is None:
                            print(f"Warning: Could not process image from {docx_path}")
                            continue

                        output_filename = f"{prefix} {current_number}.png"
                        output_path = os.path.join(output_dir, output_filename)
                        img.save(output_path, 'PNG', optimize=True)
                        all_extracted_files.append(output_path)
                        current_number += 1
            except Exception as e:
                print(f"Warning: Could not process file {docx_path}: {e}")
                continue

        return len(all_extracted_files), all_extracted_files


# Natural-key sort for the fallback path — keeps "image2.png" before
# "image10.png" instead of after. Only used when document-order parsing
# fails, but worth getting right because the alternative is the bug we
# just fixed.
def _natural_key(s: str):
    return [int(x) if x.isdigit() else x.lower()
            for x in re.split(r'(\d+)', s)]


# Standalone usage example
if __name__ == "__main__":
    extractor = ImageExtractor()

    docx_file = "example.docx"
    output_directory = "extracted_images"

    if os.path.exists(docx_file):
        count, files = extractor.extract_images_from_docx(docx_file, output_directory)
        print(f"Extracted {count} images:")
        for f in files:
            print(f"  - {f}")
    else:
        print(f"File not found: {docx_file}")
