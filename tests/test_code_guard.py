"""코드 삭제 가드 훅 (마스터 지시 2026-11-02)"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "code_guard.py"
spec = importlib.util.spec_from_file_location("code_guard", HOOK)
cg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cg)


def scan(cmd):
    return cg.scan(cmd, ROOT)


class TestProtected(unittest.TestCase):
    def test_code_and_rules_are_protected(self):
        for r in ("radar/pulse.py", "scripts/fit/stepwise.py", ".claude/hooks/chiip_guard.py", "config/discovery.yaml", "docs/tasks/chiip-pulse.md", "CLAUDE.md"):
            self.assertTrue(cg.protected(r), r)

    def test_outputs_and_caches_are_not(self):
        for r in ("outputs/report/x.html", "radar/state/a.json", "radar/__pycache__/a.py", "knowledge/models/companies/co-x/datapack.json"):
            self.assertFalse(cg.protected(r), r)


class TestScan(unittest.TestCase):
    def test_delete_commands_are_caught(self):
        for cmd in ("rm radar/pulse.py", "rm -rf radar", 'Remove-Item -Recurse -Force "radar"', "del radar\\pulse.py", "git rm radar/pulse.py", "rm radar/pul*.py",
                    "mv radar/pulse.py D:/x.py", "Clear-Content radar/pulse.py", "echo x > radar/pulse.py", "find scripts -name '*.py' -delete",
                    "bash -c \"rm radar/pulse.py\"", "py -c \"import os; os.remove('radar/pulse.py')\"", "ls; rm radar/pulse.py", "cd radar && rm pulse.py", "rm -rf ."):
            self.assertTrue(scan(cmd), cmd)

    def test_harmless_commands_pass(self):
        for cmd in ("ls radar", "git status", "git log -5", "rm radar/state/없는파일.json", "py radar/pulse.py", "echo x > 없는파일.txt", "git mv radar/pulse.py radar/p.py",
                    "git diff > /dev/null", "git config --get core.hooksPath", "git stash list", "git restore --staged radar/pulse.py", "git push origin main", 'echo "rm radar/pulse.py"'):
            self.assertEqual(scan(cmd), [], cmd)

    def test_angle_bracket_in_commit_message_passes(self):
        self.assertEqual(scan('git log; echo "a <b@c.com>" 2>/dev/null; ls'), [])

    def test_bash_style_windows_path(self):
        self.assertTrue(scan("rm /" + str(ROOT / "radar/pulse.py").replace("\\", "/").replace(":", "", 1)))

    def test_dangerous_git(self):
        for cmd in ("git clean -fd", "git reset --hard", "git checkout -- .", "git checkout HEAD -- radar/pulse.py", "git restore radar/pulse.py", "git stash", "git stash drop",
                    "git push --force origin main", "git push origin +main", "git commit --no-verify -m x", "git config core.hooksPath /dev/null", 'git -C "x" clean -f',
                    "git filter-branch --all", "git branch -D x"):
            self.assertTrue(scan(cmd), cmd)


class TestGit(unittest.TestCase):
    """임시 저장소로 커밋 검사·복구를 돌린다"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / "radar").mkdir()
        (self.root / "radar" / "a.py").write_text("print(1)\n", encoding="utf-8")
        (self.root / "radar" / "b.py").write_text("print(2)\n", encoding="utf-8")
        (self.root / "radar" / "c.txt").write_text("자료\n", encoding="utf-8")
        for args in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"]):
            subprocess.run(["git", *args], cwd=self.root, check=True)

    def hook(self, mode, event, attended="1"):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root), "CLAUDE_CODE_SESSION_ATTENDED": attended}
        r = subprocess.run([sys.executable, str(HOOK), mode], input=json.dumps(event).encode(), capture_output=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def pre(self, cmd, mode="auto", tool_id="t1"):
        return self.hook("pre", {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(self.root), "permission_mode": mode, "tool_use_id": tool_id})

    def post(self, tool_id="t1"):
        return self.hook("post", {"tool_name": "Bash", "tool_input": {}, "hook_event_name": "PostToolUse", "tool_use_id": tool_id})

    def test_delete_is_denied_in_every_mode(self):
        for mode in ("default", "auto", "acceptEdits", "bypassPermissions"):
            self.assertEqual(self.pre("rm radar/a.py", mode)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.pre("ls"), {})

    def test_script_delete_is_restored(self):
        self.pre("py 지우는스크립트.py")
        (self.root / "radar" / "a.py").unlink()
        (self.root / "radar" / "c.txt").unlink()
        out = self.post()
        self.assertEqual((self.root / "radar" / "a.py").read_text(encoding="utf-8"), "print(1)\n")
        self.assertTrue((self.root / "radar" / "c.txt").exists())   # 추적 파일도 복구(마스터 지시 2026-11-04)
        self.assertIn("radar/a.py", out["hookSpecificOutput"]["additionalContext"])

    def test_only_pruned_reports_may_go(self):
        (self.root / "radar" / "state").mkdir(parents=True, exist_ok=True)
        (self.root / "radar" / "state" / "pruned.txt").write_text("2026-11-04T00:00:00+09:00\tradar/c.txt\n", encoding="utf-8")
        self.pre("py 지우는스크립트.py")
        (self.root / "radar" / "c.txt").unlink()
        self.post()
        self.assertFalse((self.root / "radar" / "c.txt").exists())

    def test_file_already_gone_is_left_alone(self):
        (self.root / "radar" / "a.py").unlink()
        self.pre("ls")
        self.assertEqual(self.post(), {})
        self.assertFalse((self.root / "radar" / "a.py").exists())

    def test_commit_with_code_delete_asks(self):
        subprocess.run(["git", "rm", "-q", "radar/b.py"], cwd=self.root, check=True)
        self.assertIn("radar/b.py", self.pre('git commit -m "x"')["hookSpecificOutput"]["permissionDecisionReason"])

    def test_no_snapshot_is_quiet(self):
        self.assertEqual(self.post("없음"), {})


class TestFileSave(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.file = self.root / "radar" / "a.py"
        self.file.parent.mkdir()
        self.file.write_text("".join(f"x{i} = {i}\n" for i in range(40)), encoding="utf-8")

    def run_pre(self, tool, ti, rel=None, attended="1"):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root), "CLAUDE_CODE_SESSION_ATTENDED": attended}
        event = {"tool_name": tool, "tool_input": {"file_path": str(rel or self.file), **ti}, "cwd": str(self.root), "permission_mode": "auto"}
        r = subprocess.run([sys.executable, str(HOOK), "pre"], input=json.dumps(event).encode(), capture_output=True, env=env)
        return r.stdout.decode()

    def test_emptying_is_denied(self):
        self.assertIn("deny", self.run_pre("Write", {"content": ""}))

    def test_big_shrink_asks_only_when_someone_is_there(self):
        self.assertIn("ask", self.run_pre("Write", {"content": "x = 1\n"}))
        self.assertIn("deny", self.run_pre("Write", {"content": "x = 1\n"}, attended="0"))

    def test_normal_edit_passes(self):
        self.assertEqual(self.run_pre("Edit", {"old_string": "x1 = 1", "new_string": "x1 = 2"}), "")
        self.assertEqual(self.run_pre("Write", {"content": "".join(f"y{i}\n" for i in range(35))}), "")

    def test_edit_removing_most_lines_asks(self):
        body = self.file.read_text(encoding="utf-8")
        self.assertIn("ask", self.run_pre("Edit", {"old_string": body, "new_string": "x = 1\n"}))

    def test_settings_must_keep_hooks(self):
        s = self.root / ".claude" / "settings.json"
        s.parent.mkdir()
        s.write_text('{"a": "chiip_guard.py code_guard.py"}', encoding="utf-8")
        self.assertIn("deny", self.run_pre("Write", {"content": "{}"}, s))
        self.assertEqual(self.run_pre("Write", {"content": '{"b": "chiip_guard.py code_guard.py"}'}, s), "")
        self.assertIn("deny", self.run_pre("Write", {"content": '{"disableAllHooks": true, "b": "chiip_guard.py code_guard.py"}'}, s))


if __name__ == "__main__":
    unittest.main()
