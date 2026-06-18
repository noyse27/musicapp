"""
Generates logo.png and logo.ico for AdolarRadio from the SVG.
Run once before building: python make_icon.py

Requires: cairosvg Pillow
  pip install cairosvg Pillow
"""
import sys
import os

OUT_PNG = os.path.join(os.path.dirname(__file__), "logo.png")
OUT_ICO = os.path.join(os.path.dirname(__file__), "logo.ico")
SVG_SRC = os.path.join(os.path.dirname(__file__), "logo.svg")

def main():
    try:
        import cairosvg
        from PIL import Image
        import io
    except ImportError:
        print("Missing deps — run: pip install cairosvg Pillow")
        sys.exit(1)

    png_bytes = cairosvg.svg2png(url=SVG_SRC, output_width=256, output_height=256)

    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    img.save(OUT_PNG)
    print(f"Saved {OUT_PNG}")

    img.save(OUT_ICO, format="ICO", sizes=[(256,256),(64,64),(32,32),(16,16)])
    print(f"Saved {OUT_ICO}")

if __name__ == "__main__":
    main()
