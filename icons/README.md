# App icons

Logo idea: a gold arrow breaking out of the top of the opening range (the box with three small candles). Original artwork.

| file | use |
| --- | --- |
| `icon.svg` | source, full square. Content sits inside the 80% safe zone, so it works as a maskable icon |
| `logo.svg` | same, with rounded corners, for pages and previews |
| `icon-192.png`, `icon-512.png` | PWA manifest icons (`any maskable`) |
| `apple-touch-icon.png` | iPhone home screen (180x180) |
| `favicon-32.png` | browser tab |

PWA manifest snippet for the dashboard app (later):

```json
"icons": [
  { "src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable" },
  { "src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable" }
]
```

For an APK through apk-factory, use `icon-512.png`.

Rebuild the PNGs after editing the SVG:

```bash
rsvg-convert -w 512 -h 512 icon.svg -o icon-512.png
rsvg-convert -w 192 -h 192 icon.svg -o icon-192.png
rsvg-convert -w 180 -h 180 icon.svg -o apple-touch-icon.png
rsvg-convert -w 32 -h 32 logo.svg -o favicon-32.png
```
