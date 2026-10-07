"""Result card PDFs: Jinja2 fills the template, WeasyPrint renders it to PDF bytes.

Fonts are bundled in the repo (`app/assets/fonts`) rather than relying on whatever happens to be
installed on the host, so the card renders identically in dev, CI, and Docker. Noto Sans covers Latin
text; Noto Nastaliq Urdu is the fallback so a student or father's name typed in Urdu still renders
correctly instead of showing tofu boxes.
"""

import base64
import uuid
from datetime import date
from io import BytesIO
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from app.schemas.results import ResultOut

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


def _font_uri(filename: str) -> str:
    path = FONTS_DIR / filename
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:font/ttf;base64,{data}"


def _image_data_uri(path_or_url: str | None, upload_dir: str) -> str | None:
    """Best-effort: only embeds local uploads (logo/photo), and never fails the PDF if the file
    is missing - the card just renders without that image."""
    if not path_or_url:
        return None
    try:
        filename = path_or_url.rsplit("/", 1)[-1]
        local_path = Path(upload_dir) / filename
        if not local_path.is_file():
            return None
        ext = local_path.suffix.lstrip(".").lower() or "png"
        data = base64.b64encode(local_path.read_bytes()).decode("ascii")
        return f"data:image/{ext};base64,{data}"
    except OSError:
        return None


def render_result_card_html(
    result: ResultOut,
    *,
    school_name: str,
    slogan: str | None,
    address: str | None,
    phone: str | None,
    logo_url: str | None,
    photo_url: str | None,
    upload_dir: str,
    show_rank: bool,
) -> str:
    template = _env.get_template("result_card.html.jinja")
    is_draft = not result.is_published
    position = None
    if show_rank and result.rank and result.total_ranked:
        position = f"{result.rank} of {result.total_ranked}"
    return template.render(
        font_regular=_font_uri("NotoSans-Regular.ttf"),
        font_bold=_font_uri("NotoSans-Bold.ttf"),
        font_urdu=_font_uri("NotoNastaliqUrdu-Regular.ttf"),
        is_draft=is_draft,
        school_name=school_name,
        slogan=slogan,
        address=address,
        phone=phone,
        logo_src=_image_data_uri(logo_url, upload_dir),
        photo_src=_image_data_uri(photo_url, upload_dir),
        student_name=result.student_name,
        father_name=result.father_name,
        roll_no=result.roll_no,
        class_name=result.class_name,
        section_name=result.section_name,
        exam_name=result.exam_name,
        academic_year_label=result.academic_year_label,
        subjects=[s.model_dump() for s in result.subjects],
        total_marks_obtained=result.total_obtained,
        total_marks_possible=result.total_possible,
        percentage=result.percentage,
        grade=result.grade,
        is_pass=result.is_pass,
        position=position,
        remarks=result.remarks,
        card_no=f"RC-{str(result.id)[:8].upper()}",
        issued_date=date.today().isoformat(),
    )


def html_to_pdf(html: str) -> bytes:
    return HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf()


def merge_pdfs(pdf_bytes_list: list[bytes]) -> bytes:
    """Used by 'Download all cards': one PDF, one page per student."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    for data in pdf_bytes_list:
        writer.append(BytesIO(data))
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def new_share_token() -> str:
    return uuid.uuid4().hex
