import logging
import re
from pathlib import Path
from typing import Dict, Optional

from dvc.annotations import Artifact
from dvc.dvcfile import PROJECT_FILE
from dvc.exceptions import InvalidArgumentError
from dvc.repo import Repo
from dvc.utils import relpath
from dvc.utils.serialize import modify_yaml

logger = logging.getLogger(__name__)


# Constants are taken from GTO.
# When we make it a dependency, we can import them instead
SEPARATOR_IN_NAME = ":"
DIRNAME = r"[a-z0-9-_./]+"
NAME = r"[a-z0-9]([a-z0-9-/]*[a-z0-9])?"
NAME_RE = re.compile(f"^{NAME}$")
FULLNAME = f"((?P<dirname>{DIRNAME}){SEPARATOR_IN_NAME})?(?P<name>{NAME})"
FULLNAME_RE = re.compile(f"^{FULLNAME}$")


def name_is_compatible(name: str) -> bool:
    return bool(NAME_RE.search(name))


wrong_name_message = (
    "Can't use '%s' as artifact name (ID)."
    " You can use letters and numbers, and use '-' as separator"
    " (but not at the start or end)."
)


def check_name_format(name: str) -> None:
    if not name_is_compatible(name):
        logger.warning(
            wrong_name_message,
            name,
        )


def check_for_nested_dvc_repo(dvcfile: Path):
    if dvcfile.is_absolute():
        raise InvalidArgumentError("Use relative path to dvc.yaml.")
    path = dvcfile.parent
    while path.name:
        if (path / Repo.DVC_DIR).is_dir():
            raise InvalidArgumentError(
                f"Nested DVC repos like {path} are not supported."
            )
        path = path.parent


class Artifacts:
    def __init__(self, repo: "Repo") -> None:
        self.repo = repo

    def read(self) -> Dict[str, Dict[str, Artifact]]:
        artifacts: Dict[str, Dict[str, Artifact]] = {}
        for (
            dvcfile,
            dvcfile_artifacts,
        ) in self.repo.index._artifacts.items():  # pylint: disable=protected-access
            dvcyaml = relpath(dvcfile, self.repo.root_dir)
            artifacts[dvcyaml] = {}
            for name, value in dvcfile_artifacts.items():
                check_name_format(name)
                artifacts[dvcyaml][name] = Artifact(**value)
        return artifacts

    def add(self, name: str, artifact: Artifact, dvcfile: Optional[str] = None):
        # this doesn't update it "in place": self.read() won't return the updated value
        with self.repo.scm_context(quiet=True):
            if not name_is_compatible(name):
                raise InvalidArgumentError(wrong_name_message % name)
            dvcyaml = Path(dvcfile or PROJECT_FILE)
            check_for_nested_dvc_repo(
                dvcyaml.relative_to(self.repo.root_dir)
                if dvcyaml.is_absolute()
                else dvcyaml
            )

            with modify_yaml(dvcyaml) as data:
                artifacts = data.setdefault("artifacts", {})
                artifacts.update({name: artifact.to_dict()})

            self.repo.scm_context.track_file(dvcfile)

        return artifacts.get(name)
