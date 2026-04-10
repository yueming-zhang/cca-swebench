# Git Worktree + Sapling Workflow

Simple workflow: create an isolated worktree, make changes, bring them back to main, push.
No branches — just commits, the Sapling way.

## Step 1: Create a worktree from main

```bash
# From the main repo (e.g., /workspaces/cca-swebench)
sudo git worktree add --detach ../<worktree-name>
```

Example:
```bash
sudo git worktree add --detach ../cca-chat
```

This creates `/workspaces/cca-chat` at a detached HEAD pointing to `main`. No branch created.

> **Note:** If you see a "not owned by current user" error when running commands
> in the worktree, fix it with:
> ```bash
> git config --global --add safe.directory /workspaces/<worktree-name>
> ```

## Step 2: Make changes and commit in the worktree

```bash
cd /workspaces/<worktree-name>

# ... make your changes ...

sl add .
sl commit -m "Your commit message"
sl whereami   # grab the commit hash
```

> **Important:** Use `sl commit` (new commit), NOT `sl amend`.
> `sl amend` fails on public commits (already pushed) with
> "abort: cannot amend public commits".

## Step 3: Bring changes back to main

```bash
cd /workspaces/cca-swebench

# Go to the new commit (use hash from Step 2)
sl goto <COMMIT_HASH>

# Verify
sl smartlog
```

## Step 4: Push and clean up

```bash
# Push
sl push

# Remove the worktree
git worktree remove /workspaces/<worktree-name>
```
