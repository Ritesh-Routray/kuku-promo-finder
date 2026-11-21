# Deploying to Hugging Face Spaces (free)

You do these steps yourself (they need your accounts and tokens).

1. **Create a Hugging Face account** at huggingface.co and two access tokens (Settings → Access Tokens):
   - a **write** token (for uploading the demo and pushing the Space)
   - a **read** token (the Space uses it to pull the private demo)
2. **Upload the Kuku results to a private dataset** (from this folder):
   ```powershell
   # add HF_TOKEN=<write token> to .env first
   .venv\Scripts\python scripts\publish_demo.py --run outputs\kuku_full --repo <username>/kuku-promo-demo
   ```
   The script refuses to upload if the dataset is public.
3. **Create the Space:** huggingface.co/new-space → SDK **Docker** → blank template → hardware **CPU basic (free)** → Public.
4. **Add Space secrets** (Space → Settings → Variables and secrets):
   | Name | Value |
   |---|---|
   | `GEMINI_API_KEY` | your Gemini key |
   | `GROQ_API_KEY` | your Groq key |
   | `HF_TOKEN` | the **read** token |
   | `DEMO_DATASET` | `<username>/kuku-promo-demo` |
   | `ACCESS_CODE` | any code you choose; put it in the submission form |
5. **Push the code** (the scripts and outputs are gitignored, so they are not pushed):
   ```powershell
   git init; git add .; git commit -m "Promo Finder"
   git remote add space https://huggingface.co/spaces/<username>/promo-finder
   git push space main
   ```
   The first build takes ~10 minutes (it installs CPU torch and downloads the two local models).
6. Open the Space, pick the 🔒 run, enter the access code.

**Check before submitting:** open the Space in a private browser window; confirm the Space's *Files* tab has no `.txt` scripts and no `outputs/`.

---

## Free option used for the submission: static Space with encrypted demo

Hugging Face now requires PRO for Docker Spaces, so the submitted link is a **static** Space:
the same React app, with the Kuku run baked in as AES-256-GCM ciphertext (key = PBKDF2-SHA256 of
`ACCESS_CODE`, 600k iterations). The browser decrypts after the visitor enters the code; the public
Space files contain no readable script text. Live analysis of a new show runs locally (see README).

```powershell
# ACCESS_CODE in .env must be long and random (the ciphertext is public); HF_TOKEN = write token
.venv\Scripts\python scripts\build_static.py --run outputs\kuku_full --out build\static --publish <username>/promo-finder
```

The full Docker app (with live upload-and-run) can go to Google Cloud Run once billing is active:
`gcloud run deploy promo-finder --source <code-only folder> --port 7860 --memory 2Gi --max-instances 1`.
