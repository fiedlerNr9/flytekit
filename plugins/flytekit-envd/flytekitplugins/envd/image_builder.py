import pathlib
import shutil
import subprocess
from typing import Optional

import click

from flytekit.configuration import DefaultImages
from flytekit.core import context_manager
from flytekit.image_spec.image_spec import ImageBuildEngine, ImageSpec, ImageSpecBuilder


class EnvdImageSpecBuilder(ImageSpecBuilder):
    """
    This class is used to build a docker image using envd.
    """

    def build_image(self, image_spec: ImageSpec, tag: str, source_root: Optional[str] = None):
        cfg_path = self.create_envd_config(image_spec, source_root)
        command = f"envd build --path {pathlib.Path(cfg_path).parent}"
        if image_spec.registry:
            command += f" --output type=image,name={image_spec.registry}/{image_spec.name}:{tag},push=true"
        click.secho(f"Run command: {command} ", fg="blue")
        p = subprocess.Popen(command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for line in iter(p.stdout.readline, ""):
            if p.poll() is not None:
                break
            if line.decode().strip() != "":
                click.secho(line.decode().strip(), fg="blue")

        if p.returncode != 0:
            _, stderr = p.communicate()
            raise Exception(
                f"failed to build the imageSpec at {cfg_path} with error {stderr}",
            )

    def create_envd_config(self, image_spec: ImageSpec, source_root: Optional[str] = None) -> str:
        if image_spec.base_image is None:
            image_spec.base_image = DefaultImages.default_image()
        if image_spec.packages is None:
            image_spec.packages = []
        if image_spec.apt_packages is None:
            image_spec.apt_packages = []
        if image_spec.env is None:
            image_spec.env = {}
        image_spec.env.update({"PYTHONPATH": "/root"})

        envd_config = f"""# syntax=v1

def build():
    base(image="{image_spec.base_image}", dev=False)
    install.python_packages(name = [{', '.join(map(str, map(lambda x: f'"{x}"', image_spec.packages)))}])
    install.apt_packages(name = [{', '.join(map(str, map(lambda x: f'"{x}"', image_spec.apt_packages)))}])
    install.python(version="{image_spec.python_version}")
    runtime.environ(env={image_spec.env})
"""

        ctx = context_manager.FlyteContextManager.current_context()
        cfg_path = ctx.file_access.get_random_local_path("build.envd")
        pathlib.Path(cfg_path).parent.mkdir(parents=True, exist_ok=True)

        if image_spec.source_root:
            shutil.copytree(image_spec.source_root, pathlib.Path(cfg_path).parent, dirs_exist_ok=True)
            envd_config += f'    io.copy(host_path="./", envd_path="/root")'

        with open(cfg_path, "w+") as f:
            f.write(envd_config)

        return cfg_path


ImageBuildEngine.register("envd", EnvdImageSpecBuilder())