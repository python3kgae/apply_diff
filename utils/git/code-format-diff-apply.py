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
import subprocess
import sys
import tempfile
from functools import cached_property

import github
from github import IssueComment, PullRequest


def apply_patches(args: argparse.Namespace) -> None:
    repo = github.Github(args.token).get_repo(args.repo)
    pr = repo.get_issue(args.issue_number).as_pull_request()

    patch_path = os.path.join("/home/runner/work/format",f"{args.issue_number}")
    if not os.path.exists(patch_path):
        raise(f"Patch path {patch_path} does not exist")

    for patch_file in os.listdir(patch_path):
        if patch_file.endswith(".patch"):
            # run git apply patch_file
            apply_cmd = [
                "git",
                "apply",
                os.path.join(patch_path, patch_file)
            ]
            print(f"Running: {' '.join(apply_cmd)}")
            proc = subprocess.run(apply_cmd, capture_output=True)
            if proc.returncode != 0:
                raise(f"Failed to apply patch {patch_file}")

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

    args = parser.parse_args()

    apply_patches(args)
