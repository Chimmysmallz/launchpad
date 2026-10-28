# Contributing to LaunchPad

Thank you for helping. LaunchPad stays small on purpose, so a few ground rules keep it easy for anyone to run.

## Principles

1. **No required dependencies.** Everything must run on plain Python 3.8 or newer. Optional extras, such as the QR code package, must fail gracefully when they are missing.
2. **One server file.** `launchpad.py` holds the server and `static/dashboard.html` holds the interface. Please do not add a build step.
3. **Never touch a user's files.** A linked folder is read-only to LaunchPad. Nothing outside `data/` is ever deleted.
4. **Plain language in the interface.** Messages should tell people what happened and what to do next.

## Getting set up

```sh
git clone https://github.com/YOUR-USERNAME/launchpad.git
cd launchpad
python launchpad.py
```

## Before you open a pull request

- Run the tests: `python -m unittest discover -s tests -v`
- Add a test for any new behaviour in `tests/test_smoke.py`
- Try it on a phone if your change affects how apps are served
- Add a line to `CHANGELOG.md` under **Unreleased**

## Reporting bugs

Open an issue with the bug report template. Include your operating system, your Python version, and the steps that cause the problem.
