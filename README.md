# CloudFormation Practical Trainer (web version)

Practice for the 2-hour "fill in the CloudFormation template" practical.
Runs in your browser. No AWS sandbox, no sign-up, no typing commands.

---

## Start it

- **Windows:** double-click `start.bat`
- **Mac:** double-click `start.command`. If macOS says it is from an unidentified developer, right-click it, choose **Open**, then **Open** again (first time only).
- **Linux:** run `./start.command`

First run installs what it needs (about a minute).
Then your browser opens at `http://localhost:47651` (it picks the next free port automatically if that one is busy; the black window shows the exact address).

Needs **Python 3.9+** installed ([python.org](https://www.python.org/downloads/)).
On Windows, tick **"Add python.exe to PATH"** in the installer.

To stop: press **Quit** in the page, or close the black window.

---

## What's in it

- **Drills** - 8 fill-in-the-blank templates from your labs, plus 3 bug hunts
- **Exam** - random template, real countdown, hints and solution locked until you finish
- **Free practice** - paste any template to lint and score it
- **Flashcards** - 60 cards, missed ones come back more often
- **Snippets** - tested blocks for the "extra complexity" marks
- **Stats** - your completed drills and times

---

## Using a drill

1. Pick a drill
2. Fill every `____N____` in the editor
3. Pause typing and a quick check runs (lint + requirements)
4. Press **Check** (or Ctrl+Enter) for the full grade, including the mock deploy
5. Click any lint message to jump to its line
6. Once it passes, open the **Complexity** tab for what to add next

Your work saves automatically. Closing the page and coming back resumes it.

---

## How grading works

- **cfn-lint** - the real linter. Errors must be zero.
- **Requirements** - drill-specific logic (e.g. "NAT sits in a public subnet")
- **Mock deploy** - deploys into moto, a fake AWS, as a smoke test
- **Complexity score** - my own checklist out of 100

---

## Honest limits

- **cfn-lint is the strong check.** A mock-deploy failure with clean lint may be moto's fault.
- **The complexity score is not your lecturer's rubric.** Use it for ideas.
- **I haven't seen your real exam template.** These drills match the lab style.
- **Nothing here checks that an AMI id or key pair really exists.** Use the AMI your lecturer gives you, or an SSM reference.
- **IAM roles are likely blocked in the Learner Lab.** Don't plan your extra marks around creating one.
- **A pass here is not a real deploy.** If you get sandbox time, deploy your final stack once.
- **`Fn::Sub isn't needed` warnings are harmless.** The labs use `!Sub` in UserData without variables.

---

## Rule for the real thing

- Get the **base template deploying first**
- Add **one** extra at a time
- Re-check after each
- A broken ambitious template scores worse than a clean plain one

---

## Privacy

The server only listens on your own computer (`127.0.0.1`).
Nothing is sent anywhere. Progress is stored in `progress.json` and `work/`.
