import logging
import subprocess
from os import path
from pathlib import Path
from subprocess import CalledProcessError, TimeoutExpired
from typing import Optional, Union, Any, List, Dict, ClassVar, Iterable

from os_win.exceptions import OSWinException
from os_win.utils.compute.vmutils import VMUtils

from golem.core.common import get_golem_path
from golem.docker import smbshare
from golem.docker.client import local_client
from golem.docker.config import CONSTRAINT_KEYS
from golem.docker.hypervisor.docker_machine import DockerMachineHypervisor
from golem.docker.task_thread import DockerBind

logger = logging.getLogger(__name__)


class HyperVHypervisor(DockerMachineHypervisor):

    DRIVER_NAME: ClassVar[str] = 'hyperv'
    OPTIONS = dict(
        mem='--hyperv-memory',
        cpu='--hyperv-cpu-count',
        disk='--hyperv-disk-size',
        no_virt_mem='--hyperv-disable-dynamic-memory',
        boot2docker_url='--hyperv-boot2docker-url',
        virtual_switch='--hyperv-virtual-switch'
    )
    SUMMARY_KEYS = dict(
        memory_size='MemoryUsage',
        cpu_count='NumberOfProcessors'
    )
    BOOT2DOCKER_URL = "https://github.com/golemfactory/boot2docker/releases/" \
                      "download/v18.06.0-ce%2Bdvm-v0.35/boot2docker.iso"
    DOCKER_USER = "golem-docker"
    DOCKER_PASSWORD = "golem-docker"
    VIRTUAL_SWITCH = "Golem Switch"
    VOLUME_DRIVER = "cifs"

    GET_IP_SCRIPT_PATH = \
        path.join(get_golem_path(), 'scripts', 'get-ip-address.ps1')
    SCRIPT_TIMEOUT = 5  # seconds

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._vm_utils = VMUtils()

    # pylint: disable=arguments-differ
    def _parse_create_params(
            self,
            cpu: Optional[Union[str, int]] = None,
            mem: Optional[Union[str, int]] = None,
            **params: Any) -> List[str]:

        args = super()._parse_create_params(**params)
        args += [self.OPTIONS['boot2docker_url'], self.BOOT2DOCKER_URL,
                 self.OPTIONS['virtual_switch'], self.VIRTUAL_SWITCH,
                 self.OPTIONS['no_virt_mem']]

        if cpu is not None:
            args += [self.OPTIONS['cpu'], str(cpu)]
        if mem is not None:
            args += [self.OPTIONS['mem'], str(mem)]

        return args

    def constraints(self, name: Optional[str] = None) -> Dict:
        name = name or self._vm_name
        try:
            summary = self._vm_utils.get_vm_summary_info(name)
            return {k: summary[v] for k, v in self.SUMMARY_KEYS.items()}
        except (OSWinException, KeyError):
            logger.exception(
                f'Hyper-V: reading configuration of VM "{name}" failed')
            return {}

    def constrain(self, name: Optional[str] = None, **params) -> None:
        name = name or self._vm_name
        mem = params.get(CONSTRAINT_KEYS['mem'])
        cpu = params.get(CONSTRAINT_KEYS['cpu'])

        try:
            self._vm_utils.update_vm(
                vm_name=name,
                memory_mb=mem,
                memory_per_numa_node=0,
                vcpus_num=cpu,
                vcpus_per_numa_node=0,
                limit_cpu_features=False,
                dynamic_mem_ratio=0
            )
        except OSWinException:
            logger.exception(f'Hyper-V: reconfiguration of VM "{name}" failed')

        logger.info('Hyper-V: reconfiguration of VM "%s" finished', name)

    def update_work_dir(self, work_dir: Path) -> None:
        super().update_work_dir(work_dir)
        # Ensure that working directory is shared via SMB
        smbshare.create_share(self.DOCKER_USER, work_dir)

    @classmethod
    def _get_ip_for_sharing(cls) -> str:
        """
        Get IP address of the host machine which could be used for sharing
        directories with Hyper-V VMs connected to Golem's virtual switch.
        """
        try:
            return subprocess\
                .run(
                    [
                        'powershell.exe',
                        '-ExecutionPolicy', 'RemoteSigned',
                        '-File', cls.GET_IP_SCRIPT_PATH,
                        '-Interface', cls.VIRTUAL_SWITCH,
                    ],
                    timeout=10,  # seconds
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )\
                .stdout\
                .decode('utf8')\
                .strip()
        except (CalledProcessError, TimeoutExpired) as exc:
            raise RuntimeError(exc.stderr.decode('utf8'))

    @staticmethod
    def uses_volumes() -> bool:
        return True

    def create_volumes(self, binds: Iterable[DockerBind]) -> dict:
        my_ip = self._get_ip_for_sharing()
        return {
            self._create_volume(my_ip, bind.source): {
                'bind': bind.target,
                'mode': bind.mode
            }
            for bind in binds
        }

    def _create_volume(self, my_ip: str, shared_dir: Path) -> str:
        assert self._work_dir is not None
        try:
            relpath = shared_dir.relative_to(self._work_dir)
        except ValueError:
            raise ValueError(
                f'Cannot create docker volume: "{shared_dir}" is not a '
                f'subdirectory of docker work dir ("{self._work_dir}")')

        share_name = smbshare.get_share_name(self._work_dir)
        volume_name = f'{my_ip}/{share_name}/{relpath.as_posix()}'

        # Client must be created here, do it in __init__() will not work since
        # environment variables are not set yet when __init__() is called
        client = local_client()
        client.create_volume(
            name=volume_name,
            driver=self.VOLUME_DRIVER,
            driver_opts={
                'username': self.DOCKER_USER,
                'password': self.DOCKER_PASSWORD
            }
        )

        return volume_name
