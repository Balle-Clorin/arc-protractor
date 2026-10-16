# Arc Protractor Generator

Streamlit app that generates a true-scale arc protractor for a pivoted tonearm.
The effective length **L** is fixed; the pivot-to-spindle distance (**P2S**) is free.

Two ways to use it:

- **Choose an alignment** (Löfgren A, Löfgren B, Stevenson or custom null points): P2S is calculated from L.
- **Set pivot-to-spindle**: type the P2S you actually have. The null points follow, placed for lowest average error,
  lowest distortion, an inner null at the innermost groove, or an inner null you choose.

With L and P2S fixed, the null radii always satisfy `r1 * r2 = L^2 - P2S^2`.

## Output

- Sheet with the tip-path arc, radius ticks (every 5 mm), grid patches at both null points (long lines parallel to the
  cantilever), spindle crosshair with centring rings, and a 100 mm scale bar. PDF and SVG are exactly paper size.
- Tracking-error plot across the record, with the null points marked.

Print at **100% / actual size** (no fit-to-page) and check the 100 mm bar before punching the spindle hole.

## Adjusting from a miss at the outer groove

Turn the printed protractor until the stylus is on the arc at 60 mm, then read the miss X (mm) at 146 mm along the arm
(positive = past the arc, away from the pivot).

- Arm base can move: actual P2S = protractor P2S + X / k_p2s, with k_p2s = sin(a2 - a1) / sin(a1).
- P2S is fixed: change the overhang by X / k_ovh, with k_ovh = sin(a2) / sin(a1) - 1. Increase it for positive X.
- a1 and a2 are the angles at the arm pivot, cos(a) = (P2S^2 + L^2 - r^2) / (2 * P2S * L), at r = 60 and 146 mm.

For L = 233.15 mm and P2S = 214 mm: k_p2s = 1.56 (P2S change = 0.64 X) and k_ovh = 1.43 (overhang change = 0.70 X).
The app also has a calculator that solves the exact geometry.

## Run locally

    pip install -r requirements.txt
    streamlit run app.py

## Deploy

Push `app.py` and `requirements.txt` to a GitHub repo, then create the app on Streamlit Community Cloud
(main file: `app.py`).

## Geometry

Spindle at the origin, pivot at distance d, stylus at radius r and distance L from the pivot:

    sin(err + delta) = (L^2 + r^2 - d^2) / (2 L r)
    sin(delta)       = (r1 + r2) / (2 L)
    r1 * r2          = L^2 - d^2

Published null points for IEC groove radii (60.325 to 146.05 mm): Löfgren A 66.0 / 120.9,
Löfgren B 70.3 / 116.6, Stevenson 60.325 / 117.42.

Defaults are the SME V: L = 233.15 mm, P2S = 215.35 mm.

## License

PolyForm Noncommercial License 1.0.0. Add the `LICENSE` file from your other repos.
