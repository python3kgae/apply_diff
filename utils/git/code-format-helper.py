#!/usr/bin/env python3
#
# ====- code-format-helper, runs code formatters from the ci --*- python -*--==#
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#
# ==-------------------------------------------------------------------------==#

import argparse
import os
import re
import subprocess
import sys
import tempfile
from functools import cached_property

import github
from github import IssueComment, PullRequest

LF = '\n'
CRLF = '\r\n'
CR = '\r'

class FormatHelper:
    COMMENT_TAG = "<!--LLVM CODE FORMAT COMMENT: {fmt}-->"
    name = "unknown"

    @property
    def comment_tag(self) -> str:
        return self.COMMENT_TAG.replace("fmt", self.name)

    def format_run(self, changed_files: [str], args: argparse.Namespace) -> str | None:
        pass

    def pr_comment_text(self, diff: str) -> str:
        return f"""
{self.comment_tag}

:warning: {self.friendly_name}, {self.name} found issues in your code. :warning:

<details>
<summary>
You can test this locally with the following command:
</summary>

``````````bash
{self.instructions}
``````````

</details>

<details>
<summary>
View the diff from {self.name} here.
</summary>

``````````diff
{diff}
``````````

</details>

- [ ] Check this box to apply formatting changes to this branch."""

    def find_comment(
        self, pr: PullRequest.PullRequest
    ) -> IssueComment.IssueComment | None:
        for comment in pr.as_issue().get_comments():
            if self.comment_tag in comment.body:
                return comment
        return None

    def update_pr(self, diff: str, pr: PullRequest.PullRequest):
        existing_comment = self.find_comment(pr)
        pr_text = self.pr_comment_text(diff)

        if existing_comment:
            existing_comment.edit(pr_text)
        else:
            pr.as_issue().create_comment(pr_text)

    def update_pr_success(self, pr: PullRequest.PullRequest):
        existing_comment = self.find_comment(pr)
        if existing_comment:
            existing_comment.edit(
                f"""
{self.comment_tag}
:white_check_mark: With the latest revision this PR passed the {self.friendly_name}.
"""
            )
    
    def apply_diff(self, diff: str, pr: PullRequest.PullRequest):
        # git add remote for pr.head.repo.full_name
        remote_cmd = [
            "git",
            "remote",
            "add",
            "pr",
            pr.head.repo.html_url
        ]
        print(f"Running: {' '.join(remote_cmd)}")
        proc = subprocess.run(remote_cmd, capture_output=True)
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr)
            raise(f"Failed to add remote for {pr.head.repo.full_name}")
        # git fetch pr.head.ref
        fetch_cmd = [
            "git",
            "fetch",
            "pr",
            pr.head.ref
        ]
        print(f"Running: {' '.join(fetch_cmd)}")
        proc = subprocess.run(fetch_cmd, capture_output=True)
        if proc.returncode != 0:
            raise(f"Failed to fetch {pr.head.ref}")
        # git checkout pr.head.ref
        checkout_cmd = [
            "git",
            "checkout",
            pr.head.ref
        ]
        print(f"Running: {' '.join(checkout_cmd)}")
        proc = subprocess.run(checkout_cmd, capture_output=True)
        if proc.returncode != 0:
            raise(f"Failed to checkout {pr.head.ref}")

        # create a temporary file
        with tempfile.NamedTemporaryFile() as tmp:
            # force to linux line endings
            diff = diff.replace(CRLF, LF).replace(CR, LF)
            tmp.write(diff.encode("utf-8"))
            tmp.flush()

            # run git apply tmp.name
            apply_cmd = [
                "git",
                "apply",
                tmp.name
            ]
            print(f"Running: {' '.join(apply_cmd)}")
            proc = subprocess.run(apply_cmd, capture_output=True)
            if proc.returncode != 0:
                print(proc.stdout)
                print(proc.stderr)
                raise(f"Failed to apply diff from {self.name}")

        # run git add .
        add_cmd = [
            "git",
            "add",
            "."
        ]
        print(f"Running: {' '.join(add_cmd)}")
        proc = subprocess.run(add_cmd, capture_output=True)
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr)
            raise(f"Failed to add files to commit")   

    def run(self, changed_files: [str], args: argparse.Namespace):
        diff = self.format_run(changed_files, args)

        repo = github.Github(args.token).get_repo(args.repo)
        pr = repo.get_issue(args.issue_number).as_pull_request()
        if diff:
            if not args.apply_diff:
                self.update_pr(diff, pr)
                return False
            else:
                self.apply_diff(diff, pr)
        # If we get here, we have successfully formatted the code
        self.update_pr_success(pr)
        return True

class ClangFormatHelper(FormatHelper):
    name = "clang-format"
    friendly_name = "C/C++ code formatter"

    @property
    def instructions(self):
        return " ".join(self.cf_cmd)

    @cached_property
    def libcxx_excluded_files(self):
        return [] # HLSL Change - libcxx is not in DXC's repo
        #with open("libcxx/utils/data/ignore_format.txt", "r") as ifd:
        #    return [excl.strip() for excl in ifd.readlines()]

    def should_be_excluded(self, path: str) -> bool:
        if path in self.libcxx_excluded_files:
            print(f"Excluding file {path}")
            return True
        return False

    def filter_changed_files(self, changed_files: [str]) -> [str]:
        filtered_files = []
        for path in changed_files:
            _, ext = os.path.splitext(path)
            if ext in (".cpp", ".c", ".h", ".hpp", ".hxx", ".cxx"):
                if not self.should_be_excluded(path):
                    filtered_files.append(path)
        return filtered_files

    def format_run(self, changed_files: [str], args: argparse.Namespace) -> str | None:
        cpp_files = self.filter_changed_files(changed_files)
        if not cpp_files:
            return
        cf_cmd = [
            "git-clang-format",
            "--diff",
            args.start_rev,
            args.end_rev,
            "--",
        ] + cpp_files
        print(f"Running: {' '.join(cf_cmd)}")
        self.cf_cmd = cf_cmd
        proc = subprocess.run(cf_cmd, capture_output=True)

        # formatting needed
        if proc.returncode == 1:
            return proc.stdout.decode("utf-8")

        return None


class DarkerFormatHelper(FormatHelper):
    name = "darker"
    friendly_name = "Python code formatter"

    @property
    def instructions(self):
        return " ".join(self.darker_cmd)

    def filter_changed_files(self, changed_files: [str]) -> [str]:
        filtered_files = []
        for path in changed_files:
            name, ext = os.path.splitext(path)
            if ext == ".py":
                filtered_files.append(path)

        return filtered_files

    def format_run(self, changed_files: [str], args: argparse.Namespace) -> str | None:
        py_files = self.filter_changed_files(changed_files)
        if not py_files:
            return
        darker_cmd = [
            "darker",
            "--check",
            "--diff",
            "-r",
            f"{args.start_rev}..{args.end_rev}",
        ] + py_files
        print(f"Running: {' '.join(darker_cmd)}")
        self.darker_cmd = darker_cmd
        proc = subprocess.run(darker_cmd, capture_output=True)

        # formatting needed
        if proc.returncode == 1:
            return proc.stdout.decode("utf-8")

        return None

ALL_FORMATTERS = (DarkerFormatHelper(), ClangFormatHelper())

class FormatRunner:
    def __init__(self, changed_files: [str], args: argparse.Namespace):
        self.changed_files = changed_files
        self.args = args
        
        repo = github.Github(args.token).get_repo(args.repo)
        self.pr = repo.get_issue(args.issue_number).as_pull_request()

        if args.comment_id:
            comment = self.pr.get_issue_comment(args.comment_id)
            if comment is None:
                raise Exception(f"Comment {args.comment_id} does not exist")
            format_pat = re.compile(r"<!--LLVM CODE FORMAT COMMENT: (?P<FMT>.+)-->")
            m = re.match(format_pat, comment.body)
            if m is None:
                raise Exception(f"Could not find format in comment {args.comment_id}")
            fmt = m.group("FMT")
            if fmt == "clang-format":
                self.formatters = (ClangFormatHelper())
            elif fmt == "darker":
                self.formatters = (DarkerFormatHelper())
            else:
                raise Exception(f"Unknown format {fmt}")
        else:
            self.formatters = ALL_FORMATTERS

    def run(self):
        exit_code = 0
        for fmt in self.formatters:
            if not fmt.run(self.changed_files, self.pr):
                exit_code = 1

        sys.exit(exit_code)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--token", type=str, required=True, help="GitHub authentiation token"
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=os.getenv("GITHUB_REPOSITORY", "llvm/llvm-project"),
        help="The GitHub repository that we are working with in the form of <owner>/<repo> (e.g. llvm/llvm-project)",
    )
    parser.add_argument("--issue-number", type=int, required=True)
    parser.add_argument(
        "--start-rev",
        type=str,
        required=True,
        help="Compute changes from this revision.",
    )
    parser.add_argument(
        "--end-rev", type=str, required=True, help="Compute changes to this revision"
    )
    parser.add_argument(
        "--changed-files",
        type=str,
        help="Comma separated list of files that has been changed",
    )
    parser.add_argument(
        "--apply-diff",
        type=bool,
        required=True,
        help="Apply the diff to the head branch",
    )

    parser.add_argument("--comment-id", type=int, required=False)

    args = parser.parse_args()

    changed_files = []
    if args.changed_files:
        changed_files = args.changed_files.split(",")

    FormatRunner(changed_files, args).run()
