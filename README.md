# IB SA Mock Interview Evaluation Bot
### Pareeksha Gurukul | Selection Lab | Vishwas GS Academy

---

## Files
```
bot.py            ← Main bot logic
database.py       ← JSON-based data storage
pdf_generator.py  ← PDF report generation
requirements.txt  ← Python dependencies
nixpacks.toml     ← Railway Python 3.11 config
railway.toml      ← Railway deploy config
```

---

## Railway Deployment Steps

### 1. Create GitHub Repo
- Create a new **private** repo on GitHub
- Upload all these files to the root of the repo

### 2. Create Railway Project
- Go to https://railway.app
- Click **New Project → Deploy from GitHub repo**
- Select your repo

### 3. Set Environment Variables
In Railway dashboard → your service → **Variables** tab, add:

| Variable   | Value                          |
|------------|-------------------------------|
| BOT_TOKEN  | Your Telegram bot token (from @BotFather) |
| GROUP_ID   | Your admin group chat ID (negative number e.g. -1001234567890) |
| DB_PATH    | data/db.json                  |
| PDF_DIR    | data/pdfs                     |

### 4. Add Persistent Volume (Important!)
- In Railway → your service → **Volumes** tab
- Click **Add Volume**
- Mount path: `/app/data`
- This ensures DB and PDFs survive redeploys

### 5. Deploy
- Railway auto-deploys on every GitHub push
- Check **Logs** tab to confirm bot started

---

## How to Get GROUP_ID
1. Add your bot to the admin group
2. Send any message in the group
3. Visit: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
4. Look for `"chat":{"id": -100XXXXXXXXX}` — that's your GROUP_ID

---

## Commands
- `/start` — Begin evaluation flow
- `/download` — Search and download a student report
- `/cancel` — Cancel current flow

---

## Scoring Logic
- 10 sections, each scored **0–5**
- Total per interviewer: **50 marks**
- Minimum **2 evaluators** required for final report
- Maximum **4 evaluators** allowed
- Sections can be **skipped** (shown as — in PDF)
- Section average = only evaluators who scored that section
- Final verdict: **40+/50 = Good**, below 40 = Improvement needed
