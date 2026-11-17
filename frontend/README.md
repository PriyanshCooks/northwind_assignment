# Review UI

Plain static files (no build step, no npm), served by `app/main.py` at `/ui`. Start it with `python run.py serve`
and open http://127.0.0.1:8000/. `app.js` holds the router, the API helper and the runs list; `steps.js` holds the
six step views. Server text is put on the page with `textContent`, never as HTML.
