from pathlib import Path

from conftest import write_entry

from entry_rules import (
    validate_code_uses_opik,
    validate_folder_name,
    validate_meta,
    validate_no_secrets,
    validate_proof,
    validate_readme,
)


def test_valid_meta_has_no_errors(tmp_path: Path):
    entry = write_entry(tmp_path)
    assert validate_meta(entry) == []


def test_missing_meta_file_is_error(tmp_path: Path):
    entry = tmp_path / "no_meta"
    entry.mkdir()
    errors = validate_meta(entry)
    assert any("meta.yaml" in e for e in errors)


def test_missing_required_field_is_error(tmp_path: Path):
    entry = write_entry(tmp_path, meta={"title": None})
    assert any("title" in e for e in validate_meta(entry))


def test_empty_required_field_is_error(tmp_path: Path):
    entry = write_entry(tmp_path, meta={"description": "  "})
    assert any("description" in e for e in validate_meta(entry))


def test_links_must_have_one_http_value(tmp_path: Path):
    entry = write_entry(tmp_path, meta={"links": {"repo": "not-a-url"}})
    assert any("link" in e.lower() for e in validate_meta(entry))


def test_invalid_platform_is_error(tmp_path: Path):
    entry = write_entry(tmp_path, meta={"opik_platform": "on-prem"})
    assert any("opik_platform" in e for e in validate_meta(entry))


def test_hosted_must_be_bool(tmp_path: Path):
    entry = write_entry(tmp_path, meta={"hosted": "yes"})
    assert any("hosted" in e for e in validate_meta(entry))


def test_tags_must_be_list(tmp_path: Path):
    entry = write_entry(tmp_path, meta={"tags": "agent"})
    assert any("tags" in e for e in validate_meta(entry))


def test_malformed_yaml_is_reported(tmp_path: Path):
    entry = tmp_path / "bad_yaml"
    entry.mkdir()
    (entry / "meta.yaml").write_text("title: [unclosed\n")
    errors = validate_meta(entry)
    assert any("meta.yaml" in e for e in errors)


def test_valid_readme_has_no_errors(tmp_path: Path):
    entry = write_entry(tmp_path)
    assert validate_readme(entry) == []


def test_missing_readme_is_error(tmp_path: Path):
    entry = tmp_path / "no_readme"
    entry.mkdir()
    assert any("README.md" in e for e in validate_readme(entry))


def test_missing_section_is_error(tmp_path: Path):
    readme = "# Title\n\n## What I built\nStuff.\n\n## Problem it solves\nX.\n"
    entry = write_entry(tmp_path, readme=readme)
    errors = validate_readme(entry)
    assert any("What I learned" in e for e in errors)
    assert any("How I used Opik" in e for e in errors)


def test_placeholder_body_is_error(tmp_path: Path):
    readme = (
        "# T\n\n## What I built\nTODO\n\n## Problem it solves\nX.\n\n"
        "## What I learned\nY.\n\n## How I used Opik\nZ.\n"
    )
    entry = write_entry(tmp_path, readme=readme)
    assert any("What I built" in e for e in validate_readme(entry))


def test_empty_section_body_is_error(tmp_path: Path):
    readme = (
        "# T\n\n## What I built\n\n## Problem it solves\nX.\n\n"
        "## What I learned\nY.\n\n## How I used Opik\nZ.\n"
    )
    entry = write_entry(tmp_path, readme=readme)
    assert any("What I built" in e for e in validate_readme(entry))


def test_valid_proof_has_no_errors(tmp_path: Path):
    entry = write_entry(tmp_path)
    assert validate_proof(entry) == []


def test_missing_png_is_error(tmp_path: Path):
    entry = write_entry(tmp_path, include_png=False)
    assert any("opik-proof.png" in e for e in validate_proof(entry))


def test_png_not_referenced_is_error(tmp_path: Path):
    readme = (
        "# T\n\n## What I built\nA.\n\n## Problem it solves\nB.\n\n"
        "## What I learned\nC.\n\n## How I used Opik\nNo image here.\n"
    )
    entry = write_entry(tmp_path, readme=readme)
    assert any("referenced" in e.lower() for e in validate_proof(entry))


def test_valid_folder_name_ok(tmp_path: Path):
    entry = write_entry(tmp_path, slug="jane_agent")
    assert validate_folder_name(entry) == []


def test_bad_folder_name_is_error(tmp_path: Path):
    entry = write_entry(tmp_path, slug="JaneAgent")
    assert any("folder name" in e.lower() for e in validate_folder_name(entry))


def test_folder_name_without_underscore_is_error(tmp_path: Path):
    entry = write_entry(tmp_path, slug="janeagent")
    assert any("folder name" in e.lower() for e in validate_folder_name(entry))


def test_clean_entry_has_no_secret_findings(tmp_path: Path):
    entry = write_entry(tmp_path)
    assert validate_no_secrets(entry) == []


def test_dotenv_file_is_flagged(tmp_path: Path):
    entry = write_entry(tmp_path)
    (entry / ".env").write_text("OPIK_API_KEY=abc\n")
    assert any(".env" in e for e in validate_no_secrets(entry))


def test_dotenv_example_is_not_flagged(tmp_path: Path):
    entry = write_entry(tmp_path)
    (entry / ".env.example").write_text("OPIK_API_KEY=\n")
    assert validate_no_secrets(entry) == []


def test_hardcoded_key_is_flagged(tmp_path: Path):
    entry = write_entry(
        tmp_path,
        code={"app.py": 'client = OpenAI(api_key="sk-abcdefghijklmnopqrstuvwxyz123456")\n'},
    )
    assert any("hardcoded" in e.lower() or "key" in e.lower() for e in validate_no_secrets(entry))


def test_sk_proj_key_is_flagged(tmp_path: Path):
    entry = write_entry(
        tmp_path,
        code={"app.py": 'client = OpenAI(api_key="sk-proj-abcdefghijklmnopqrstuvwxyz012345")\n'},
    )
    assert any("hardcoded" in e.lower() or "key" in e.lower() for e in validate_no_secrets(entry))


def test_hosted_without_opik_usage_is_error(tmp_path: Path):
    entry = write_entry(
        tmp_path,
        meta={"hosted": True},
        code={"app.py": "def run():\n    return 1\n"},
    )
    assert any("opik" in e.lower() for e in validate_code_uses_opik(entry))


def test_hosted_with_opik_usage_ok(tmp_path: Path):
    entry = write_entry(
        tmp_path,
        meta={"hosted": True},
        code={"app.py": "import opik\n\n@opik.track\ndef run():\n    return 1\n"},
    )
    assert validate_code_uses_opik(entry) == []


def test_listed_entry_skips_code_check(tmp_path: Path):
    entry = write_entry(tmp_path, meta={"hosted": False})
    assert validate_code_uses_opik(entry) == []


def test_non_ascii_readme_and_meta_are_read_as_utf8(tmp_path: Path):
    readme = (
        "# 支持代理 — Real-time support agent’s Opik tracing\n\n"
        "## What I built\n"
        "一个通过 RAG 索引回答账单问题的支持代理 — built with love.\n\n"
        "## Problem it solves\n"
        "客服代表花费数小时处理重复的账单问题。\n\n"
        "## What I learned\n"
        "Opik’s span metadata made it obvious which retrieval step was dropping context.\n\n"
        "## How I used Opik\n"
        "Traced each agent turn with `@opik.track` — see the screenshot:\n\n"
        "![Opik traces](opik-proof.png)\n"
    )
    entry = write_entry(
        tmp_path,
        readme=readme,
        meta={
            "title": "支持代理 — Real-time support agent",
            "description": "客服支持代理 — traced end-to-end with an LLM-judge eval loop’s help.",
        },
    )
    assert validate_readme(entry) == []
    assert validate_meta(entry) == []


def test_proof_url_without_png_passes(tmp_path: Path):
    readme = (
        "# T\n\n## What I built\nA.\n\n## Problem it solves\nB.\n\n"
        "## What I learned\nC.\n\n## How I used Opik\n"
        "See the author's traces: https://example.com/opik.png\n"
    )
    entry = write_entry(
        tmp_path,
        readme=readme,
        include_png=False,
        meta={"proof_url": "https://example.com/opik.png"},
    )
    assert validate_proof(entry) == []


def test_non_http_proof_url_without_png_is_error(tmp_path: Path):
    entry = write_entry(
        tmp_path,
        include_png=False,
        meta={"proof_url": "see my repo"},
    )
    assert any("proof" in e.lower() for e in validate_proof(entry))


def test_schemeless_http_proof_url_without_png_is_error(tmp_path: Path):
    entry = write_entry(
        tmp_path,
        include_png=False,
        meta={"proof_url": "httpfoo-not-a-url"},
    )
    assert any("proof" in e.lower() for e in validate_proof(entry))


def test_no_png_and_no_proof_url_is_error(tmp_path: Path):
    entry = write_entry(tmp_path, include_png=False)
    errors = validate_proof(entry)
    assert any("opik-proof.png" in e or "proof_url" in e for e in errors)
