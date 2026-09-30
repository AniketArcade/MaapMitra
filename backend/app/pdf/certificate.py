"""Certificate PDF + QR rendering (step 8).

ASSUMPTION: the layout below is illustrative demo content, not a legally mandated certificate
format. Verify with a domain expert before any non-demo use — the same caveat
core/instrument_types.py and core/inspection_templates.py already carry for their own content.
"""

import io
from datetime import date

import segno
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.core.instrument_types import TYPE_LABELS, InstrumentType


def qr_png_bytes(url: str, *, scale: int = 6) -> bytes:
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="png", scale=scale)
    return buf.getvalue()


def qr_code_data_uri(url: str, *, scale: int = 6) -> str:
    return segno.make(url, error="m").png_data_uri(scale=scale)


def render(
    snapshot: dict,
    *,
    certificate_number: str,
    valid_from: date,
    valid_until: date,
    data_hash: str,
    verify_url: str,
) -> bytes:
    """One-page certificate: header, instrument + business details, validity, QR, hash."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    left = 25 * mm
    y = height - 25 * mm

    c.setFont("Helvetica-Bold", 18)
    c.drawString(left, y, "Certificate of Verification")
    y -= 8 * mm
    c.setFont("Helvetica", 11)
    c.drawString(left, y, "Legal Metrology Verification & Digital Certification Platform")
    y -= 12 * mm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(left, y, f"Certificate number: {certificate_number}")
    y -= 10 * mm

    rows = [
        ("Instrument UID", snapshot["instrument_uid"]),
        ("Type", TYPE_LABELS[InstrumentType(snapshot["instrument_type"])]),
        ("Manufacturer", snapshot["manufacturer"]),
        ("Model", snapshot["model"]),
        ("Serial number", snapshot["serial_number"]),
        ("Capacity", f"{snapshot['capacity']} {snapshot['capacity_unit']}"),
        ("Accuracy class", snapshot["accuracy_class"] or "Not specified"),
        ("Address", snapshot["address"]),
        ("Region", f"{snapshot['district_name']}, {snapshot['state_name']}"),
        ("Owner", snapshot["organization_name"]),
        ("Application number", snapshot["application_number"]),
        ("Approved by", snapshot["approved_by_name"]),
        ("Valid from", valid_from.isoformat()),
        ("Valid until", valid_until.isoformat()),
    ]
    c.setFont("Helvetica", 10)
    for label, value in rows:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left, y, f"{label}:")
        c.setFont("Helvetica", 10)
        c.drawString(left + 45 * mm, y, str(value))
        y -= 6 * mm

    y -= 6 * mm
    qr_size = 35 * mm
    c.drawImage(
        ImageReader(io.BytesIO(qr_png_bytes(verify_url))),
        left,
        y - qr_size,
        width=qr_size,
        height=qr_size,
    )
    c.setFont("Helvetica", 8)
    c.drawString(left + qr_size + 5 * mm, y - 5 * mm, "Scan to verify this certificate online.")
    c.drawString(left + qr_size + 5 * mm, y - 10 * mm, f"Verification hash: {data_hash[:16]}")

    c.showPage()
    c.save()
    return buf.getvalue()
