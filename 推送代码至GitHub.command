#!/bin/bash
# LaTeX 简历工坊：安全绑定并推送到独立 GitHub 仓库
# 目标仓库：https://github.com/zyf2492313716-cloud/latex-resume-studio

set -euo pipefail

cd "$(dirname "$0")"

TARGET_OWNER="zyf2492313716-cloud"
TARGET_REPO="latex-resume-studio"
TARGET_HTTPS="https://github.com/${TARGET_OWNER}/${TARGET_REPO}.git"
TARGET_SSH="git@github.com:${TARGET_OWNER}/${TARGET_REPO}.git"
FORBIDDEN_LOCAL="/Users/zhouyufeng/opencode/web/resume-generator"

clear
echo -e "\033[1;36m==========================================================================\033[0m"
echo -e "       \033[1;32m LaTeX 简历工坊：安全推送到独立 GitHub 仓库\033[0m"
echo -e "==========================================================================\033[0m"
echo "本脚本只用于当前独立项目，不会推送到旧的 resume-generator 项目。"
echo "目标仓库：${TARGET_HTTPS}"
echo ""

if [ ! -d ".git" ]; then
  echo -e "\033[1;33m当前目录还不是 Git 仓库，正在初始化。\033[0m"
  git init
  git branch -M main
fi

current_origin="$(git remote get-url origin 2>/dev/null || true)"
if [ -n "$current_origin" ]; then
  echo "当前 origin：$current_origin"
  if [[ "$current_origin" == "$FORBIDDEN_LOCAL"* ]] || [[ "$current_origin" == *"resume-generator"* && "$current_origin" != *"${TARGET_REPO}"* ]]; then
    echo -e "\033[1;31m检测到 origin 指向旧项目或旧仓库，必须改为新仓库后才能继续。\033[0m"
  fi
fi

echo ""
echo "将 origin 设置为：${TARGET_HTTPS}"
read -r -p "确认继续？输入 YES 后回车：" CONFIRM
if [ "$CONFIRM" != "YES" ]; then
  echo "已取消，没有修改远程仓库。"
  exit 0
fi

if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$TARGET_HTTPS"
else
  git remote add origin "$TARGET_HTTPS"
fi

new_origin="$(git remote get-url origin)"
if [ "$new_origin" != "$TARGET_HTTPS" ] && [ "$new_origin" != "$TARGET_SSH" ]; then
  echo -e "\033[1;31morigin 校验失败：$new_origin\033[0m"
  exit 1
fi

echo -e "\033[1;32morigin 已安全绑定到 ${TARGET_REPO}\033[0m"
echo ""

echo "即将暂存当前项目文件并创建提交。"
read -r -p "输入提交信息，直接回车使用默认值：" COMMIT_MSG
COMMIT_MSG=${COMMIT_MSG:-"chore: rebrand as LaTeX Resume Studio"}

git add .
if git diff --cached --quiet; then
  echo "没有待提交的变更，跳过 commit。"
else
  git commit -m "$COMMIT_MSG"
fi

echo ""
echo "准备推送到 origin main：$new_origin"
read -r -p "确认推送？输入 PUSH 后回车：" PUSH_CONFIRM
if [ "$PUSH_CONFIRM" != "PUSH" ]; then
  echo "已取消推送；本地提交已保留。"
  exit 0
fi

git push -u origin main

echo "--------------------------------------------------------------------------"
echo -e "\033[1;32m已推送到独立仓库。\033[0m"
echo -e "https://github.com/${TARGET_OWNER}/${TARGET_REPO}"
echo ""
echo "发布 DMG 时请使用 GitHub Releases，并上传 dist-desktop 中生成的 LaTeX 简历工坊 DMG。"
echo -e "\033[1;36m==========================================================================\033[0m"
read -r -p "按回车键退出..." _
