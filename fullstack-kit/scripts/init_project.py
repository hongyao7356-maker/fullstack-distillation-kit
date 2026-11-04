#!/usr/bin/env python3
"""Create a private workspace, never overwrite an existing file."""
import argparse
import json
from pathlib import Path


def initialize(project: Path, profile_name: str = "generic") -> list[str]:
    project = project.resolve()
    if not project.is_dir():
        raise ValueError(f"Project directory missing: {project}")
    kit = Path(__file__).resolve().parents[1]
    src = kit / "templates" / ("profile_digital_employee.json" if profile_name == "digital-employee" else "profile_generic.json")
    if not src.is_file():
        raise RuntimeError("Missing profile template")
    workspace = project / ".fullstack"
    for name in ("docs", "evidence", "checks", "reviews", "sources", "cards"):
        (workspace / name).mkdir(parents=True, exist_ok=True)
    created = []
    dst = workspace / "profile.json"
    # Exclusive creation prevents overwriting on repeated runs.
    try:
        with dst.open("x", encoding="utf-8") as fh:
            data = json.loads(src.read_text(encoding="utf-8"))
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        created.append(str(dst))
    except FileExistsError:
        pass
    guide = workspace / "WORKSPACE_README.md"
    try:
        with guide.open("x", encoding="utf-8") as fh:
            fh.write("# 全栈工程证据目录\n\n")
            fh.write("docs 为阶段文档；evidence 为命令记录；checks 为执行日志；reviews 为独立审查报告。\n")
            fh.write("这些文件不代表自动验证了业务正确性。优先按项目隐私和版本控制要求管理。\n")
        created.append(str(guide))
    except FileExistsError:
        pass
    return created


def main():
    parser = argparse.ArgumentParser(description="Initialize .fullstack without overwriting anything")
    parser.add_argument("--project", default=".")
    parser.add_argument("--profile", choices=["generic", "digital-employee"], default="generic")
    args = parser.parse_args()
    for item in initialize(Path(args.project), args.profile):
        print("CREATED", item)
    print("OK: workspace initialized or already exists; inspect .fullstack/profile.json")


if __name__ == "__main__":
    main()
