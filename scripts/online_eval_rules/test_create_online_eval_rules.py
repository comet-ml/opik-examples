import create_online_eval_rules as cli


def test_parser_parses_create_llm_judge():
    args = cli.build_parser().parse_args(["create-llm-judge", "--name", "r1", "--dry-run"])
    assert args.command == "create-llm-judge"
    assert args.name == "r1"
    assert args.dry_run is True


def test_parser_defaults_surface_to_sdk():
    args = cli.build_parser().parse_args(["list"])
    assert args.surface == "sdk"
