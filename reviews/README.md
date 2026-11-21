# Independent reviews

ChatGPT reviews specifications, completed build steps and gate reports. ChatGPT has no access to this repository, so Ben relays each request and answer.

## How it works

1. Claude writes a request in `reviews/requests/NNN-short-name.md`: what to review, which files, and the questions to answer.
2. Ben gives the request (and the files it names) to ChatGPT, and saves the answer as `reviews/responses/NNN-short-name.md` (or pastes it to Claude, who saves it unchanged).
3. Claude reproduces each finding before acting on it, then writes `reviews/responses/NNN-short-name-answer.md`: for each finding, agreed / disagreed / partly, what was changed, and why.
4. `reviews/LOG.md` keeps one line per review.

Reviews inform Ben's decisions; they do not make them.
