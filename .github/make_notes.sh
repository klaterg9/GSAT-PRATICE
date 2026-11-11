#!/bin/sh
# 배포 페이지 내용 만들기: .github/changes/<태그>.md (있으면) + 공통 안내(.github/release_notes.md)
# 사용: sh .github/make_notes.sh v1.3.0 > notes.md
tag="$1"
dir="$(dirname "$0")"
changes="$dir/changes/$tag.md"
if [ -n "$tag" ] && [ -f "$changes" ]; then
  echo "### $tag 변경 사항"
  cat "$changes"
  echo
  echo "---"
  echo
fi
cat "$dir/release_notes.md"
