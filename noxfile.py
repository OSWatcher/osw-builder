import nox

excluded = [".nox", "packer-templates"]


@nox.session
def lint(session):
    session.install("flake8", "flake8-bugbear", "isort", "mypy")
    session.run("flake8", "--show-source", "--statistics", "--exclude", ",".join(excluded))
    session.run("isort", "--line-length", "120", ".")


@nox.session
def type(session):
    session.install("-r", "requirements.txt")
    session.install("mypy")
    session.run("mypy", ".")


@nox.session
def fmt(session):
    session.install("black")
    session.run("black", "--line-length", "120", ".")


@nox.session
def run(session):
    args = session.posargs
    session.install("-r", "requirements.txt")
    session.run("python", "builder.py", *args)
