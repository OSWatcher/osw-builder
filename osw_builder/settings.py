from pathlib import Path

from dynaconf import Dynaconf

CUR_DIR = Path(__file__).parent

settings = Dynaconf(
    envvar_prefix="OSW_BUILDER",
    environments=False,
    load_dotenv=True,
    # use absolute paths to import the conf from parent modules
    # from neogit.config import settings
    settings_files=[
        str(CUR_DIR / "default_settings.yaml"),
    ],
)
