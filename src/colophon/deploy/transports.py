"""Remote upload transports for deploy.

Normalized deploy targets and built output directories flow into dry-run plans or
FTP, FTPS, SFTP, and SSHFS side effects.
"""

from __future__ import annotations

import ftplib
import posixpath
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from colophon.errors import DeployConfigError, DeployError
from colophon.models import ProjectPaths, TransportUploader


def iter_site_files(source_dir: Path) -> list[tuple[Path, str]]:
    if not source_dir.exists():
        raise DeployConfigError(f"site output directory does not exist: {source_dir}")

    return [
        (path, path.relative_to(source_dir).as_posix())
        for path in sorted(source_dir.rglob("*"))
        if path.is_file()
    ]


def is_safe_remote_purge_path(remote_path: str) -> bool:
    text = str(remote_path or "").strip()
    parts = [
        part
        for part in text.strip("/").split("/")
        if part and part not in {".", "~"}
    ]

    if text in {"", "/", ".", "~"} or len(parts) < 2:
        return False

    return not (parts[0] in {"home", "users"} and len(parts) <= 2)


def purge_enabled(target: Mapping[str, Any]) -> bool:
    value = target.get("purge", True)

    if not isinstance(value, bool):
        raise DeployConfigError("deploy target purge must be a boolean")

    return value


def require_safe_remote_purge_path(target: Mapping[str, Any]) -> None:
    remote_path = str(target.get("remote_path") or "")

    if purge_enabled(target) and not is_safe_remote_purge_path(remote_path):
        raise DeployConfigError(f"refusing to purge unsafe remote path {remote_path!r}")


def planned_upload_actions(target: Mapping[str, Any], source_dir: Path) -> list[str]:
    file_count = len(iter_site_files(source_dir))
    transport = str(target.get("transport") or "")
    remote = f"{transport}://{target.get('host')}/{target.get('remote_path')}"
    purge = "purge then upload" if purge_enabled(target) else "upload"
    return [f"{purge} {file_count} file(s) to {remote}"]


def ftp_entry_is_directory(ftp: ftplib.FTP, name: str) -> bool:
    current = ftp.pwd()

    try:
        ftp.cwd(name)
        ftp.cwd(current)
        return True
    except ftplib.all_errors:
        try:
            ftp.cwd(current)
        except ftplib.all_errors:
            pass
        return False


def purge_ftp_current_directory(ftp: ftplib.FTP) -> None:
    try:
        names = [name for name in ftp.nlst() if name not in {".", ".."}]
    except ftplib.error_perm:
        names = []

    for name in names:
        if ftp_entry_is_directory(ftp, name):
            ftp.cwd(name)
            purge_ftp_current_directory(ftp)
            ftp.cwd("..")
            ftp.rmd(name)
        else:
            ftp.delete(name)


def ensure_ftp_directory(ftp: ftplib.FTP, directory: str) -> None:
    if not directory:
        return

    current = ftp.pwd()

    for part in [part for part in directory.split("/") if part]:
        try:
            ftp.mkd(part)
        except ftplib.all_errors:
            pass
        ftp.cwd(part)

    ftp.cwd(current)


def upload_ftp_files(ftp: ftplib.FTP, source_dir: Path) -> None:
    for path, relative_path in iter_site_files(source_dir):
        ensure_ftp_directory(ftp, posixpath.dirname(relative_path))

        with path.open("rb") as handle:
            ftp.storbinary(f"STOR {relative_path}", handle)


def upload_with_ftp(target: Mapping[str, Any], source_dir: Path, dry_run: bool) -> list[str]:
    require_safe_remote_purge_path(target)
    actions = planned_upload_actions(target, source_dir)

    if dry_run:
        return actions

    ftp_class = ftplib.FTP_TLS if target.get("transport") == "ftps" else ftplib.FTP
    ftp = ftp_class()

    try:
        ftp.connect(str(target["host"]), int(target["port"]), timeout=30)
        ftp.login(str(target["username"]), str(target.get("password") or ""))

        if isinstance(ftp, ftplib.FTP_TLS):
            ftp.prot_p()

        ftp.cwd(str(target["remote_path"]))

        if purge_enabled(target):
            purge_ftp_current_directory(ftp)

        upload_ftp_files(ftp, source_dir)
        return actions
    finally:
        try:
            ftp.quit()
        except ftplib.all_errors:
            ftp.close()


def sftp_is_directory(mode: int) -> bool:
    return stat.S_ISDIR(mode)


def purge_sftp_directory(sftp: Any, remote_path: str) -> None:
    for entry in sftp.listdir_attr(remote_path):
        if entry.filename in {".", ".."}:
            continue

        child = posixpath.join(remote_path, entry.filename)

        if sftp_is_directory(entry.st_mode):
            purge_sftp_directory(sftp, child)
            sftp.rmdir(child)
        else:
            sftp.remove(child)


def ensure_sftp_directory(sftp: Any, directory: str) -> None:
    parts = [part for part in directory.strip("/").split("/") if part]
    current = "/" if directory.startswith("/") else ""

    for part in parts:
        current = posixpath.join(current, part) if current else part

        try:
            sftp.mkdir(current)
        except OSError:
            pass


def upload_sftp_files(sftp: Any, source_dir: Path, remote_path: str) -> None:
    for path, relative_path in iter_site_files(source_dir):
        target_path = posixpath.join(remote_path, relative_path)
        ensure_sftp_directory(sftp, posixpath.dirname(target_path))
        sftp.put(str(path), target_path)


def upload_with_sftp(target: Mapping[str, Any], source_dir: Path, dry_run: bool) -> list[str]:
    require_safe_remote_purge_path(target)
    actions = planned_upload_actions(target, source_dir)

    if dry_run:
        return actions

    try:
        import paramiko
    except ImportError as exc:
        raise DeployError("SFTP deploy requires the optional dependency: pip install 'colophon-site[sftp]'") from exc

    transport = paramiko.Transport((str(target["host"]), int(target["port"])))
    connect_kwargs = {"username": str(target["username"])}

    if target.get("password"):
        connect_kwargs["password"] = str(target["password"])

    try:
        transport.connect(**connect_kwargs)
        sftp = paramiko.SFTPClient.from_transport(transport)

        if purge_enabled(target):
            purge_sftp_directory(sftp, str(target["remote_path"]))

        upload_sftp_files(sftp, source_dir, str(target["remote_path"]))
        sftp.close()
        return actions
    finally:
        transport.close()


def purge_local_directory_contents(directory: Path) -> None:
    for path in directory.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def copy_site_contents(source_dir: Path, target_dir: Path) -> None:
    for path, relative_path in iter_site_files(source_dir):
        destination = target_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def upload_with_sshfs(target: Mapping[str, Any], source_dir: Path, dry_run: bool) -> list[str]:
    require_safe_remote_purge_path(target)
    actions = planned_upload_actions(target, source_dir)

    if dry_run:
        return actions

    with tempfile.TemporaryDirectory() as tmp:
        mount_point = Path(tmp) / "remote"
        mount_point.mkdir()
        remote = f"{target['username']}@{target['host']}:{target['remote_path']}"
        subprocess.run(
            ["sshfs", "-p", str(target["port"]), remote, str(mount_point)],
            check=True,
        )

        try:
            if purge_enabled(target):
                purge_local_directory_contents(mount_point)

            copy_site_contents(source_dir, mount_point)
        finally:
            subprocess.run(["umount", str(mount_point)], check=False)

    return actions


TRANSPORT_UPLOADERS: dict[str, TransportUploader] = {
    "ftp": upload_with_ftp,
    "ftps": upload_with_ftp,
    "sftp": upload_with_sftp,
    "sshfs": upload_with_sshfs,
}


def upload_site_directory(
    target: Mapping[str, Any],
    project: ProjectPaths,
    source_dir: Path | None = None,
    dry_run: bool = False,
    uploaders: Mapping[str, TransportUploader] | None = None,
) -> list[str]:
    resolved_project = project
    resolved_source_dir = resolved_project.output_dir if source_dir is None else source_dir
    registry = TRANSPORT_UPLOADERS if uploaders is None else uploaders
    transport = str(target.get("transport") or "").lower()
    uploader = registry.get(transport)

    if uploader is None:
        raise DeployConfigError(f"unknown deploy transport {transport!r}")

    return uploader(target, resolved_source_dir, dry_run)
