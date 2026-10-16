# KNRUHS Admission Notification Monitor

A small Python monitor for https://www.knruhs.telangana.gov.in/admission-notification/ that detects new notice/document links and sends Telegram alerts. GitHub Actions runs it on a scheduled workflow, with state saved in `state.json` to avoid repeat alerts.

## Important limitations

- GitHub Actions scheduled runs are best-effort. `*/5 * * * *` requests a run every five minutes but GitHub can delay or drop runs during high load. It is not a guaranteed five-minute or instant alert.
- The monitor detects newly appearing matching links. It will not alert on a changed PDF whose URL remains exactly the same, or a text-only change that doesn't add a matching link.
- The first run creates a baseline and deliberately sends no alert for links already on the page.
- The public GitHub repository contains the state file and tracked notice URLs/titles. Do not put secrets in code or `state.json`. A public repository is convenient for free scheduled Actions, but anyone can see the tracked URLs/titles.
- If the website blocks automated requests, changes structure, or renders notices with JavaScript, the monitor may need adjustments.
- Respect the website's terms and avoid excessive requests.

## Setup

### 1. Create a Telegram bot

1. Open Telegram and search for `@BotFather` (the official bot-creation bot).
2. Send `/newbot`, follow the prompts, and copy the bot token. Treat it like a password.
3. Open your new bot's chat and press **Start** or send `/start`.
4. To obtain your chat ID, open this URL in a browser, replacing `YOUR_BOT_TOKEN` with your token:
   `https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates`
5. Find `"chat":{"id":123456789,...}` in the response. The number is your `TELEGRAM_CHAT_ID`. If the result is empty, send `/start` to your bot and refresh the URL.
6. Do not share the token or post it in the repository.

### 2. Create the GitHub repository

1. Sign in at https://github.com/new.
2. Repository name: `knruhs-notification-monitor`.
3. For simplest free scheduled execution, select **Public**. You can choose Private, but check current GitHub Actions scheduling/usage restrictions for private repositories.
4. Create the repository. Do not add a README or other files if you will upload this project as-is.

### 3. Upload these project files

Upload the contents of this folder, keeping the directory structure:

- `monitor.py`
- `requirements.txt`
- `.gitignore`
- `.github/workflows/monitor.yml`
- `README.md`

On GitHub, use **Add file → Upload files**. To upload `.github/workflows/monitor.yml`, you may need to create/upload the folder structure from your computer; alternatively use **Add file → Create new file** and enter the path `.github/workflows/monitor.yml`.

### 4. Add GitHub secrets

In your repository, open:

**Settings → Secrets and variables → Actions → New repository secret**

Add these two secrets exactly:

- `TELEGRAM_BOT_TOKEN` — token from BotFather
- `TELEGRAM_CHAT_ID` — your Telegram chat ID

Never put either value directly in `monitor.py` or the workflow file.

### 5. Enable and test Actions

1. Open the repository's **Actions** tab. If prompted, enable workflows.
2. Select **KNRUHS admission page monitor**.
3. Click **Run workflow** and start it with `baseline_only` unchecked.
4. The first successful run saves the current matching links as a baseline and does not send a message.
5. Confirm that `state.json` appears in the repository after the workflow commits its state.
6. Send a test alert manually if desired: use the Actions run logs to check the monitor. The monitor only sends Telegram messages when it detects a new link, not on every run.
7. The workflow then runs on the five-minute schedule when GitHub schedules it.

### 6. Test an alert safely

Do not edit the real KNRUHS page. For a controlled test, use a separate test repository or temporarily point `TARGET_URL` to a page you control and add a new link. Restore the real URL afterwards. Do not commit tokens.

## How it avoids duplicate alerts

- The first run saves the current links without alerting.
- Later runs compare current matching URLs with saved URLs.
- It sends an alert for URLs that are new, then commits the updated `state.json`.
- If Telegram sending fails, the run fails before saving the new state, so the next run can retry.

## Troubleshooting

- **No workflow runs:** Check Actions is enabled, the default branch contains `.github/workflows/monitor.yml`, and the repository has not been inactive long enough for scheduled workflows to be disabled.
- **No Telegram alert:** Check the bot was started, both secrets are spelled correctly, and the Actions log has no Telegram API error.
- **No notices detected / no `state.json`:** Inspect the run log. The page may be unavailable or its links may not match the current extraction rules.
- **Workflow can't push state:** Ensure workflow permissions allow read/write contents and check branch protection settings.
- **Repeated alert after workflow concurrency/commit conflict:** Review `state.json` and the run logs before rerunning.
