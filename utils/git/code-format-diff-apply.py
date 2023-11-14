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

LF = '\n'
CRLF = '\r\n'
CR = '\r'


def get_diff_from_comment(comment: IssueComment.IssueComment) -> str:
    diff_pat = re.compile(r"``````````diff(?P<DIFF>.+)``````````", re.DOTALL)
    m = re.search(diff_pat, comment.body)
    if m is None:
        raise Exception(f"Could not find diff in comment {comment.id}")
    diff = m.group("DIFF")
    # force to linux line endings
    diff = diff.replace(CRLF, LF).replace(CR, LF)
    return diff

def run_cmd(cmd: [str]) -> None:
    print(f"Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise Exception(f"Failed to run {' '.join(cmd)}")

def apply_patches(args: argparse.Namespace) -> None:
    repo = github.Github(args.token).get_repo(args.repo)
    pr = repo.get_issue(args.issue_number).as_pull_request()

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

    comment = pr.get_issue_comment(args.comment_id)
    if comment is None:
        raise Exception(f"Comment {args.comment_id} does not exist")

    # get the diff from the comment
    diff = get_diff_from_comment(comment)

    # write diff to temporary file and apply
    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(diff.encode("utf-8"))
        tmp.flush()

        # run git apply tmp.name
        apply_cmd = [
            "git",
            "apply",
            tmp.name
        ]
        run_cmd(apply_cmd)

    # run git add .
    add_cmd = [
        "git",
        "add",
        "."
    ]
    run_cmd(add_cmd)

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
