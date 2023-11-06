#!/usr/bin/env python3
#
# ====- code-format-diff-apply, apply diff from comment --*- python -*-------==#
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

diff_pat = re.compile(r"``````````diff(?P<DIFF>.+)``````````", re.DOTALL)

def apply_patches(args: argparse.Namespace) -> None:
    repo = github.Github(args.token).get_repo(args.repo)
    pr = repo.get_issue(args.issue_number).as_pull_request()
    print("head repo is")
    print(pr.head.repo.full_name)
    print("head ref is")
    print(pr.head.ref)    
    comment = pr.get_issue_comment(args.comment_id)
    if comment is None:
        raise(f"Comment {args.comment_id} does not exist")

    # get the diff from the comment
    m = re.search(diff_pat, comment.body)
    if m is None:
        raise(f"Could not find diff in comment {args.comment_id}")
    diff = m.group("DIFF")

    # create a temporary file
    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(diff.encode("utf-8"))
        tmp.flush()

        # run git apply tmp.name
        apply_cmd = [
            "git",
            "apply",
            tmp.name
        ]
        print(f"Running: {' '.join(apply_cmd)}")
        proc = subprocess.run(apply_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr)
            raise(f"Failed to apply diff from comment {args.comment_id}")

    # run git add .
    add_cmd = [
        "git",
        "add",
        "."
    ]
    print(f"Running: {' '.join(add_cmd)}")
    proc = subprocess.run(add_cmd, capture_output=True)
    if proc.returncode != 0:
        raise(f"Failed to add files to commit")


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
    parser.add_argument("--comment-id", type=int, required=True)

    args = parser.parse_args()

    apply_patches(args)
