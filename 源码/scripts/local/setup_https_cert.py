import argparse
import ipaddress
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


DEFAULT_HOSTS = ["www.nstl.gov.cn", "localhost", "127.0.0.1"]


def _write_private_key(path: Path, key) -> None:
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def _write_cert(path: Path, cert: x509.Certificate) -> None:
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _load_cert(path: Path) -> x509.Certificate | None:
    if not path.exists():
        return None
    try:
        return x509.load_pem_x509_certificate(path.read_bytes())
    except Exception:
        return None


def _cert_has_hosts(cert: x509.Certificate, hosts: list[str]) -> bool:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return False

    dns_names = set(san.get_values_for_type(x509.DNSName))
    ip_addresses = {str(value) for value in san.get_values_for_type(x509.IPAddress)}
    for host in hosts:
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if host not in dns_names:
                return False
        else:
            if host not in ip_addresses:
                return False
    return True


def _needs_regeneration(cert_path: Path, hosts: list[str], force: bool) -> bool:
    if force:
        return True
    cert = _load_cert(cert_path)
    if cert is None:
        return True
    now = datetime.now(timezone.utc)
    if cert.not_valid_before_utc > now or cert.not_valid_after_utc <= now + timedelta(days=7):
        return True
    return not _cert_has_hosts(cert, hosts)


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _san_entries(hosts: list[str]) -> list[x509.GeneralName]:
    entries: list[x509.GeneralName] = []
    for host in hosts:
        try:
            entries.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            entries.append(x509.DNSName(host))
    return entries


def generate_certificates(cert_dir: Path, hosts: list[str], force: bool) -> None:
    cert_dir.mkdir(parents=True, exist_ok=True)
    server_key_path = cert_dir / "key.pem"
    server_cert_path = cert_dir / "cert.pem"

    if not _needs_regeneration(server_cert_path, hosts, force):
        print(f"Existing HTTPS certificate is valid: {server_cert_path}")
        return

    now = datetime.now(timezone.utc)

    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_subject = _name(hosts[0])
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(server_subject)
        .issuer_name(server_subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=397))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.SubjectAlternativeName(_san_entries(hosts)), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(server_key, hashes.SHA256())
    )

    _write_private_key(server_key_path, server_key)
    _write_cert(server_cert_path, server_cert)

    print(f"Generated trusted HTTPS certificate: {server_cert_path}")


def trust_ca(cert_dir: Path) -> None:
    cert_path = cert_dir / "cert.pem"
    if not cert_path.exists():
        raise FileNotFoundError(f"Missing HTTPS certificate: {cert_path}")

    result = subprocess.run(
        ["certutil", "-user", "-addstore", "Root", str(cert_path)],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise RuntimeError("Failed to trust HTTPS certificate in CurrentUser Root store")
    print("Trusted HTTPS certificate in CurrentUser Root store.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare local HTTPS certificate for web_demo.")
    parser.add_argument(
        "--cert-dir",
        default=str(Path(__file__).resolve().parents[2] / "frontend" / "web_demo"),
        help="Directory that stores cert.pem and key.pem.",
    )
    parser.add_argument("--host", action="append", dest="hosts", help="DNS name or IP to include in SAN.")
    parser.add_argument("--force", action="store_true", help="Regenerate certificate files.")
    parser.add_argument("--trust", action="store_true", help="Trust the generated local CA for current user.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cert_dir = Path(args.cert_dir).resolve()
    hosts = args.hosts or DEFAULT_HOSTS
    generate_certificates(cert_dir, hosts, args.force)
    if args.trust:
        trust_ca(cert_dir)


if __name__ == "__main__":
    main()
