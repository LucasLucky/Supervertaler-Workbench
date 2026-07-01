#!/bin/bash
# =============================================================================
# Supervertaler macOS Signed Build & Notarization Script
# =============================================================================
# Builds the .app bundle, signs it with a Developer ID certificate,
# creates a .dmg, notarizes with Apple, and staples the ticket.
#
# Usage:
#   ./build_macos_signed.sh                       # Full pipeline
#   ./build_macos_signed.sh --skip-notarize       # Build + sign only (no Apple submission)
#   ./build_macos_signed.sh --upload              # Full pipeline + upload to latest GitHub release
#   ./build_macos_signed.sh --upload v1.9.285     # Full pipeline + upload to specific tag
#   ./build_macos_signed.sh --clean               # Clean venv before building
#   ./build_macos_signed.sh --clean --upload      # Clean build + full pipeline + upload
#
# Prerequisites:
#   1. Apple Developer Program membership ($99/year)
#   2. "Developer ID Application" certificate in Keychain Access
#   3. Notarization credentials stored:
#        xcrun notarytool store-credentials "supervertaler-notarize"
#   4. Configuration file:
#        cp codesign.env.example codesign.env   (then fill in your values)
#   5. Tools:
#        brew install create-dmg gh
#        xcode-select --install
#
# See BUILD_MACOS.md for full setup instructions.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Parse arguments ──────────────────────────────────────────────────────────
CLEAN=false
UPLOAD=false
SKIP_NOTARIZE=false
RELEASE_TAG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --clean)
            CLEAN=true
            shift
            ;;
        --skip-notarize)
            SKIP_NOTARIZE=true
            shift
            ;;
        --upload)
            UPLOAD=true
            shift
            if [[ $# -gt 0 && ! "$1" =~ ^-- ]]; then
                RELEASE_TAG="$1"
                shift
            fi
            ;;
        -h|--help)
            head -30 "$0" | tail -25
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--clean] [--skip-notarize] [--upload [TAG]]"
            exit 1
            ;;
    esac
done

# ── Load signing configuration ───────────────────────────────────────────────
if [ ! -f "codesign.env" ]; then
    echo "ERROR: codesign.env not found."
    echo ""
    echo "  cp codesign.env.example codesign.env"
    echo "  # Then edit codesign.env with your Developer ID identity."
    echo ""
    echo "See BUILD_MACOS.md → 'Code Signing & Notarization' for setup."
    exit 1
fi
# shellcheck source=codesign.env.example
source codesign.env

if [ -z "${CODESIGN_IDENTITY:-}" ]; then
    echo "ERROR: CODESIGN_IDENTITY not set in codesign.env"
    exit 1
fi
if [ -z "${NOTARIZE_PROFILE:-}" ]; then
    echo "ERROR: NOTARIZE_PROFILE not set in codesign.env"
    exit 1
fi

# ── Prerequisite checks ─────────────────────────────────────────────────────
echo ""
echo "=== Supervertaler macOS Signed Build ==="
echo ""

# Check codesign tool
if ! command -v codesign &>/dev/null; then
    echo "ERROR: codesign not found. Install Xcode CLI tools:"
    echo "  xcode-select --install"
    exit 1
fi

# Check signing certificate exists in keychain
echo "Checking signing certificate..."
if ! security find-identity -v -p codesigning | grep -q "$CODESIGN_IDENTITY"; then
    echo "ERROR: Certificate not found in keychain:"
    echo "  $CODESIGN_IDENTITY"
    echo ""
    echo "Available signing identities:"
    security find-identity -v -p codesigning
    echo ""
    echo "See BUILD_MACOS.md for certificate setup instructions."
    exit 1
fi
echo "  ✓ Certificate found"

# Check notarization credentials (unless skipping)
if [ "$SKIP_NOTARIZE" = false ]; then
    echo "Checking notarization credentials..."
    if ! xcrun notarytool history --keychain-profile "$NOTARIZE_PROFILE" >/dev/null 2>&1; then
        echo "ERROR: Notarization profile '$NOTARIZE_PROFILE' not found."
        echo ""
        echo "Store your credentials first:"
        echo "  xcrun notarytool store-credentials '$NOTARIZE_PROFILE' \\"
        echo "      --apple-id 'your@email.com' \\"
        echo "      --team-id '$TEAM_ID' \\"
        echo "      --password 'xxxx-xxxx-xxxx-xxxx'"
        echo ""
        echo "Or run with --skip-notarize to sign without notarizing."
        exit 1
    fi
    echo "  ✓ Notarization credentials OK"
fi

# Check create-dmg
if ! command -v create-dmg &>/dev/null; then
    echo "ERROR: create-dmg not found."
    echo "  brew install create-dmg"
    exit 1
fi
echo "  ✓ create-dmg found"

# ── Get version from pyproject.toml ──────────────────────────────────────────
# Parse the [project] table's version with awk so this step does not depend on
# the system python3 having tomllib (only Python 3.11+ ships it; macOS system
# python3 is older). Reads the first `version = "..."` line inside [project].
VERSION=$(awk '
    /^\[/  { in_project = ($0 == "[project]") }
    in_project && /^[[:space:]]*version[[:space:]]*=/ {
        gsub(/.*=[[:space:]]*"|".*/, "")
        print
        exit
    }
' pyproject.toml)

if [ -z "$VERSION" ]; then
    echo "ERROR: Could not parse version from [project] in pyproject.toml"
    exit 1
fi
echo ""
echo "Version: v${VERSION}"
echo ""

# ── Create / activate venv ───────────────────────────────────────────────────
VENV_DIR=".venv-build-macos"

if [ "$CLEAN" = true ] && [ -d "$VENV_DIR" ]; then
    echo "Cleaning build venv..."
    rm -rf "$VENV_DIR"
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating build venv..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

echo "Installing dependencies..."
pip install --upgrade pip setuptools wheel pyinstaller -q
pip install -e . -q

# ── Generate .icns if missing ────────────────────────────────────────────────
if [ ! -f "assets/icon.icns" ]; then
    echo "Generating macOS icon..."
    mkdir -p assets/Supervertaler.iconset
    cp assets/icon_16x16.png  assets/Supervertaler.iconset/icon_16x16.png
    cp assets/icon_32x32.png  assets/Supervertaler.iconset/icon_16x16@2x.png
    cp assets/icon_32x32.png  assets/Supervertaler.iconset/icon_32x32.png
    cp assets/icon_64.png     assets/Supervertaler.iconset/icon_32x32@2x.png
    cp assets/icon_128.png    assets/Supervertaler.iconset/icon_128x128.png
    cp assets/icon_256.png    assets/Supervertaler.iconset/icon_128x128@2x.png
    cp assets/icon_256.png    assets/Supervertaler.iconset/icon_256x256.png
    sips -z 512 512 assets/icon_256.png --out assets/Supervertaler.iconset/icon_256x256@2x.png 2>/dev/null
    sips -z 512 512 assets/icon_256.png --out assets/Supervertaler.iconset/icon_512x512.png 2>/dev/null
    sips -z 1024 1024 assets/icon_256.png --out assets/Supervertaler.iconset/icon_512x512@2x.png 2>/dev/null
    iconutil -c icns assets/Supervertaler.iconset -o assets/icon.icns
    rm -rf assets/Supervertaler.iconset
    echo "Icon created: assets/icon.icns"
fi

# ── Kill any running instance ────────────────────────────────────────────────
if pgrep -x "Supervertaler" > /dev/null 2>&1; then
    echo "Stopping running Supervertaler..."
    pkill -x "Supervertaler" 2>/dev/null || true
    sleep 1
fi

# ── Clean previous build ────────────────────────────────────────────────────
if [ "$CLEAN" = true ]; then
    echo "Cleaning previous build artifacts..."
    rm -rf build/Supervertaler_macOS
fi
rm -rf dist/Supervertaler dist/Supervertaler.app

# ── Build .app bundle ────────────────────────────────────────────────────────
echo ""
echo "=== Building .app bundle ==="
pyinstaller Supervertaler_macOS.spec --noconfirm --clean

APP_PATH="dist/Supervertaler.app"

if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: Build failed — $APP_PATH not found."
    exit 1
fi

# ── Fix framework structure ──────────────────────────────────────────────────
# PyInstaller + PyQt6 sometimes creates stray Resources dirs at Versions/Resources
# (should be at Versions/A/Resources). This breaks Apple's framework validation.
echo ""
echo "=== Fixing framework structure ==="
find "$APP_PATH/Contents/Frameworks" -path "*/Versions/Resources" -type d \
    -exec rm -rf {} + 2>/dev/null || true
echo "  ✓ Framework structure cleaned"

# ── Copy bundled JRE post-PyInstaller, pre-signing ───────────────────────────
# We deliberately copy the JRE AFTER PyInstaller has finished its build,
# instead of listing it in Supervertaler_macOS.spec's datas. PyInstaller's
# macOS binary-relocation pass extracts libjli.dylib from the JRE tree out
# to Contents/Frameworks/libjli.dylib and rewrites its load commands; the
# launcher (libjli) is then incompatible with the unmodified libjvm.dylib
# still inside the JRE, the JLI→JVM call dispatches into a null function
# pointer, and the JVM crashes at init with SIGSEGV in libjli's launcher
# code (verified against hs_err_pid logs from v1.9.417's broken DMG).
#
# By copying the JRE after PyInstaller is done, both libjli and libjvm stay
# paired with their original install_names. The signing pass below picks
# up the JRE Mach-O binaries via the same find-based discovery as before.
echo ""
echo "=== Copying bundled JRE (post-PyInstaller) ==="
SRC_JRE="okapi-sidecar/dist/jre"
DST_JRE="$APP_PATH/Contents/Frameworks/okapi-sidecar/jre"
if [ -d "$SRC_JRE" ]; then
    rm -rf "$DST_JRE"
    cp -R "$SRC_JRE" "$DST_JRE"
    echo "  ✓ JRE copied to Contents/Frameworks/okapi-sidecar/jre/"
else
    echo "ERROR: Bundled JRE not found at $SRC_JRE."
    echo "       Run 'cd okapi-sidecar && bash build.sh --jlink' first."
    exit 1
fi

# ── Code signing (inside-out, hardened runtime) ──────────────────────────────
echo ""
echo "=== Code Signing ==="
echo "Identity: $CODESIGN_IDENTITY"
echo ""

# Helper function to sign a single binary (handles spaces in identity)
sign_binary() {
    local entitlements_file="$1"
    local target="$2"
    codesign --force --sign "$CODESIGN_IDENTITY" --timestamp --options runtime \
        --entitlements "$entitlements_file" "$target"
}

# Count binaries for progress reporting
SO_COUNT=$(find "$APP_PATH" -name "*.so" -type f | wc -l | tr -d ' ')
DYLIB_COUNT=$(find "$APP_PATH" -name "*.dylib" -type f | wc -l | tr -d ' ')
FW_COUNT=$(find "$APP_PATH/Contents/Frameworks" -name "*.framework" -type d | wc -l | tr -d ' ')

# Step 1: Sign all .so files (Python extensions)
echo "Signing .so libraries ($SO_COUNT files)..."
find "$APP_PATH" -name "*.so" -type f -print0 | while IFS= read -r -d '' f; do
    sign_binary "Supervertaler.entitlements" "$f"
done

# Step 2: Sign all .dylib files (native libraries)
echo "Signing .dylib libraries ($DYLIB_COUNT files)..."
find "$APP_PATH" -name "*.dylib" -type f -print0 | while IFS= read -r -d '' f; do
    sign_binary "Supervertaler.entitlements" "$f"
done

# Step 2b: Sign bundled JRE executables (Okapi sidecar)
JRE_DIR="$APP_PATH/Contents/Frameworks/okapi-sidecar/jre"
if [ -d "$JRE_DIR" ]; then
    # Find all Mach-O executables in the JRE (java, keytool, jspawnhelper, etc.)
    JRE_BINS=$(find "$JRE_DIR" -type f -perm +111 -exec file {} \; | grep "Mach-O" | cut -d: -f1)
    JRE_COUNT=$(echo "$JRE_BINS" | grep -c . || true)
    echo "Signing JRE executables ($JRE_COUNT files)..."
    echo "$JRE_BINS" | while IFS= read -r f; do
        [ -n "$f" ] && sign_binary "Supervertaler.entitlements" "$f"
    done
    echo "  ✓ JRE executables signed"
fi

# Step 3: Sign QtWebEngineProcess helper (before its parent framework)
WEBENGINE_HELPER="$APP_PATH/Contents/Frameworks/PyQt6/Qt6/lib/QtWebEngineCore.framework/Versions/A/Helpers/QtWebEngineProcess.app"
if [ -d "$WEBENGINE_HELPER" ]; then
    echo "Signing QtWebEngineProcess helper..."
    # Sign the helper executable first
    sign_binary "Supervertaler_webengine_helper.entitlements" \
        "$WEBENGINE_HELPER/Contents/MacOS/QtWebEngineProcess"
    # Then sign the helper .app bundle
    sign_binary "Supervertaler_webengine_helper.entitlements" \
        "$WEBENGINE_HELPER"
    echo "  ✓ QtWebEngineProcess signed"
else
    echo "  (QtWebEngineProcess helper not found — skipping)"
fi

# Step 4: Sign all frameworks (deepest-first via -depth)
echo "Signing frameworks ($FW_COUNT frameworks)..."
find "$APP_PATH/Contents/Frameworks" -name "*.framework" -type d -depth -print0 | while IFS= read -r -d '' f; do
    sign_binary "Supervertaler.entitlements" "$f"
done

# Step 5: Sign the main executable
echo "Signing main executable..."
sign_binary "Supervertaler.entitlements" "$APP_PATH/Contents/MacOS/Supervertaler"

# Step 6: Sign the top-level .app bundle
echo "Signing app bundle..."
sign_binary "Supervertaler.entitlements" "$APP_PATH"

# ── Verify signature ────────────────────────────────────────────────────────
echo ""
echo "=== Verifying Signature ==="

echo "Deep verification..."
if codesign --verify --deep --strict --verbose=2 "$APP_PATH" 2>&1; then
    echo "  ✓ Code signature verified OK"
else
    echo ""
    echo "ERROR: Code signature verification FAILED."
    echo "Check the output above for details."
    exit 1
fi

echo ""
echo "Gatekeeper assessment..."
if spctl --assess --type execute --verbose "$APP_PATH" 2>&1; then
    echo "  ✓ Gatekeeper accepted"
else
    echo ""
    echo "WARNING: Gatekeeper rejected the app."
    echo "This is expected before notarization. Continuing..."
fi

# ── Create DMG ───────────────────────────────────────────────────────────────
DMG_NAME="Supervertaler-v${VERSION}-macOS.dmg"
DMG_PATH="dist/${DMG_NAME}"

rm -f "$DMG_PATH"

echo ""
echo "=== Creating DMG ==="
create-dmg \
    --volname "Supervertaler" \
    --volicon "assets/icon.icns" \
    --window-pos 200 120 \
    --window-size 600 400 \
    --icon-size 100 \
    --icon "Supervertaler.app" 150 190 \
    --hide-extension "Supervertaler.app" \
    --app-drop-link 450 190 \
    "$DMG_PATH" \
    "$APP_PATH"

# Sign the DMG itself
echo "Signing DMG..."
codesign --force --sign "$CODESIGN_IDENTITY" --timestamp "$DMG_PATH"
echo "  ✓ DMG signed"

DMG_SIZE=$(du -h "$DMG_PATH" | cut -f1)

# ── Notarize ─────────────────────────────────────────────────────────────────
if [ "$SKIP_NOTARIZE" = true ]; then
    echo ""
    echo "=== Notarization SKIPPED (--skip-notarize) ==="
else
    echo ""
    echo "=== Notarizing with Apple ==="
    echo "Submitting ${DMG_NAME} (${DMG_SIZE})..."
    echo "This typically takes 2–15 minutes. Waiting..."
    echo ""

    # Submit and capture output
    SUBMIT_OUTPUT=$(xcrun notarytool submit "$DMG_PATH" \
        --keychain-profile "$NOTARIZE_PROFILE" \
        --wait 2>&1) || true

    echo "$SUBMIT_OUTPUT"
    echo ""

    # Check result
    if echo "$SUBMIT_OUTPUT" | grep -q "status: Accepted"; then
        echo "  ✓ Notarization ACCEPTED"

        # Staple the ticket to the DMG
        echo ""
        echo "Stapling notarization ticket..."
        xcrun stapler staple "$DMG_PATH"
        echo "  ✓ Ticket stapled to DMG"

        # Validate stapling
        echo ""
        echo "Validating stapled ticket..."
        xcrun stapler validate "$DMG_PATH"
        echo "  ✓ Stapled ticket valid"
    else
        echo "  ✗ Notarization FAILED"
        echo ""

        # Try to extract the submission ID and fetch the log
        SUBMISSION_ID=$(echo "$SUBMIT_OUTPUT" | grep -E "^\s*id:" | head -1 | awk '{print $NF}')
        if [ -n "$SUBMISSION_ID" ]; then
            echo "Fetching notarization log for submission $SUBMISSION_ID..."
            echo ""
            xcrun notarytool log "$SUBMISSION_ID" \
                --keychain-profile "$NOTARIZE_PROFILE" 2>&1 || true
        fi

        echo ""
        echo "Fix the issues above and re-run this script."
        echo "Tip: The signed (but un-notarized) DMG is still at: $DMG_PATH"
        exit 1
    fi
fi

# ── Final summary ────────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo "  Build Complete"
echo "========================================"
echo "  App:        $APP_PATH"
echo "  DMG:        $DMG_PATH ($DMG_SIZE)"
echo "  Signed:     YES ($CODESIGN_IDENTITY)"
if [ "$SKIP_NOTARIZE" = true ]; then
    echo "  Notarized:  NO (skipped)"
else
    echo "  Notarized:  YES (ticket stapled)"
fi
echo "========================================"
echo ""

# ── Upload to GitHub Release ─────────────────────────────────────────────────
if [ "$UPLOAD" = true ]; then
    echo "=== Uploading to GitHub Release ==="

    if ! command -v gh &>/dev/null; then
        echo "ERROR: GitHub CLI (gh) not found."
        echo "  brew install gh"
        exit 1
    fi

    if ! gh auth status > /dev/null 2>&1; then
        echo "ERROR: GitHub CLI not authenticated."
        echo "  gh auth login"
        exit 1
    fi

    # Determine release tag
    if [ -z "$RELEASE_TAG" ]; then
        RELEASE_TAG=$(gh release list --limit 1 --json tagName -q '.[0].tagName' 2>/dev/null)
        if [ -z "$RELEASE_TAG" ]; then
            echo "ERROR: No releases found. Create a release first or specify a tag:"
            echo "  $0 --upload v${VERSION}"
            exit 1
        fi
        echo "Latest release: ${RELEASE_TAG}"
    fi

    echo "Uploading ${DMG_NAME} to release ${RELEASE_TAG}..."

    # Delete existing asset with same name (for re-uploads)
    gh release delete-asset "$RELEASE_TAG" "$DMG_NAME" --yes 2>/dev/null || true

    # Upload
    gh release upload "$RELEASE_TAG" "$DMG_PATH" --clobber

    REPO_URL=$(gh repo view --json url -q '.url')
    echo ""
    echo "=== Upload Complete ==="
    echo "  Release: ${REPO_URL}/releases/tag/${RELEASE_TAG}"
    echo "  Asset:   ${DMG_NAME}"
    echo ""
fi

echo "To run the app:      open dist/Supervertaler.app"
echo "To test in terminal:  dist/Supervertaler.app/Contents/MacOS/Supervertaler"
