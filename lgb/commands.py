"""Parse and execute simulated git / LGB meta-commands.

Commands run against a :class:`~lgb.model.GitEngine`. Execution is structural
only: no index, no working-tree files (except the simplified staging model used
by a few working-dir commands if extended later).
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

from lgb.model import GitEngine, Ref


class CommandError(Exception):
    """Raised when a user command cannot be parsed or executed."""


@dataclass
class CommandResult:
    """Outcome of one logical command line.

    Attributes:
        messages: User-visible output lines.
        undone: Whether the engine asked the host to pop an undo snapshot.
        reset_level: Whether the host should reset the current level.
        show_levels: Whether the host should navigate to the level browser.
        show_solution: Whether the host should reveal the level solution.
        quit_hint: Optional soft hint rendered by the UI.
    """

    messages: list[str] = field(default_factory=list)
    undone: bool = False
    reset_level: bool = False
    show_levels: bool = False
    show_solution: bool = False
    quit_hint: str | None = None


def split_commands(line: str) -> list[str]:
    """Split a user line on ``;`` and newlines into individual commands.

    Args:
        line: Raw input, possibly containing several ``;``-separated commands.

    Returns:
        Non-empty command strings with surrounding whitespace stripped.
    """
    parts = re.split(r"[;\n]", line)
    return [p.strip() for p in parts if p.strip()]


def _tokenize(command: str) -> list[str]:
    """Tokenize a command with shell-like quoting.

    Args:
        command: Single command string.

    Returns:
        Tokens.

    Raises:
        CommandError: On unbalanced quotes.
    """
    try:
        return shlex.split(command, posix=True)
    except ValueError as exc:
        raise CommandError(str(exc)) from exc


def execute_line(eng: GitEngine, line: str, history: list[str] | None = None) -> CommandResult:
    """Execute one user line that may contain several commands.

    Args:
        eng: Engine to mutate.
        line: Raw input line.
        history: Optional list to append successful command texts to.

    Returns:
        Combined result of all commands in the line.

    Raises:
        CommandError: If any command fails. The engine may be partially updated;
            callers should restore an undo snapshot on error if needed.
    """
    result = CommandResult()
    for command in split_commands(line):
        one = execute_one(eng, command)
        result.messages.extend(one.messages)
        result.undone = result.undone or one.undone
        result.reset_level = result.reset_level or one.reset_level
        result.show_levels = result.show_levels or one.show_levels
        result.show_solution = result.show_solution or one.show_solution
        if one.quit_hint:
            result.quit_hint = one.quit_hint
        if history is not None and not one.undone and not one.reset_level:
            history.append(command)
    return result


def execute_one(eng: GitEngine, command: str) -> CommandResult:
    """Execute a single command string.

    Args:
        eng: Engine to mutate.
        command: One command without ``;`` separators.

    Returns:
        Command result.

    Raises:
        CommandError: On parse or execution failure.
    """
    tokens = _tokenize(command)
    if not tokens:
        return CommandResult()

    head = tokens[0].lower()
    if head == "git":
        return _exec_git(eng, tokens[1:])
    if head in {"undo", "reset", "levels", "solution", "show", "help", "clear", "goal", "log", "status"}:
        return _exec_meta(eng, head, tokens[1:], command)
    if head.startswith("git"):
        return _exec_git(eng, tokens[1:])
    raise CommandError(f"unknown command '{tokens[0]}'. type 'help' for a list.")


def _exec_meta(eng: GitEngine, head: str, rest: list[str], raw: str) -> CommandResult:
    """Dispatch non-git meta commands.

    Args:
        eng: Engine (used by log/status).
        head: Normalized first token.
        rest: Remaining tokens.
        raw: Original command text.

    Returns:
        Command result.

    Raises:
        CommandError: On invalid meta syntax.
    """
    if head == "undo":
        return CommandResult(messages=["undo requested"], undone=True)
    if head == "reset":
        return CommandResult(messages=["reset requested"], reset_level=True)
    if head == "levels":
        return CommandResult(messages=["opening levels"], show_levels=True)
    if head == "solution":
        return CommandResult(messages=["showing solution"], show_solution=True)
    if head == "show":
        if rest and rest[0].lower() == "solution":
            return CommandResult(messages=["showing solution"], show_solution=True)
        raise CommandError("usage: show solution")
    if head == "help":
        return CommandResult(messages=help_lines())
    if head == "clear":
        return CommandResult(messages=[])
    if head == "goal":
        return CommandResult(messages=["compare your tree to the goal tree in the sidebar"])
    if head == "log":
        return CommandResult(messages=_log_lines(eng))
    if head == "status":
        return CommandResult(messages=_status_lines(eng))
    raise CommandError(f"unhandled meta command '{raw}'")


def help_lines() -> list[str]:
    """Return sandbox / level help text.

    Returns:
        Help lines for the terminal pane.
    """
    return [
        "Learn Git Branching — Streamlit clone",
        "",
        "git commit                    create a commit on the current branch",
        "git branch <name>             create a branch at HEAD",
        "git branch -f <name> <rev>    force-move a branch",
        "git branch -d <name>          delete a branch",
        "git checkout <rev>            move HEAD to a commit or branch",
        "git checkout -b <name>        create a branch and switch to it",
        "git checkout -                switch to the previous HEAD",
        "git merge <rev>               merge a branch into the current one",
        "git rebase <rev>              rebase current branch onto <rev>",
        "git rebase --onto <to> <from> [<branch>]",
        "git cherry-pick <rev...>      copy commits onto HEAD",
        "git reset --hard <rev>        move current branch to <rev>",
        "git revert <rev>              create a commit that undoes <rev>",
        "git tag <name> [<rev>]        create a tag",
        "git clone                     create a fake remote from current repo",
        "git fetch                     update remote-tracking branches",
        "git pull / git pull --rebase  fetch + merge/rebase",
        "git push                      publish local branches to the remote",
        "git fakeTeamwork [br] [n]     teammate commits on a remote branch",
        "undo / reset / levels / show solution",
    ]


def _log_lines(eng: GitEngine) -> list[str]:
    """Build a simple log from HEAD.

    Args:
        eng: Engine to read.

    Returns:
        One line per commit: id + message + parents.
    """
    tip = eng.head_commit_id()
    lines = []
    for cid in eng.commits_inclusive_history(tip):
        commit = eng.commits[cid]
        parents = ",".join(commit.parents) if commit.parents else "root"
        marker = "*" if cid == tip else " "
        lines.append(f"{marker} {cid} ({parents}) {commit.message}")
    return lines


def _status_lines(eng: GitEngine) -> list[str]:
    """Build a short status description.

    Args:
        eng: Engine to read.

    Returns:
        Status lines for HEAD and branch tips.
    """
    if eng.head_detached:
        head = f"HEAD detached at {eng.head_target}"
    else:
        head = f"HEAD -> {eng.head_target} ({eng.branches[eng.head_target].target})"
    lines = [head, ""]
    lines.append("Local branches:")
    for name, ref in sorted(eng.branches.items()):
        lines.append(f"  {name} -> {ref.target}")
    if eng.remote_branches:
        lines.append("Remote-tracking branches:")
        for name, ref in sorted(eng.remote_branches.items()):
            lines.append(f"  {name} -> {ref.target}")
    if eng.tags:
        lines.append("Tags:")
        for name, ref in sorted(eng.tags.items()):
            lines.append(f"  {name} -> {ref.target}")
    return lines


def _exec_git(eng: GitEngine, tokens: list[str]) -> CommandResult:
    """Dispatch a ``git`` subcommand.

    Args:
        eng: Engine to mutate.
        tokens: Tokens after the ``git`` prefix.

    Returns:
        Command result.

    Raises:
        CommandError: On unknown subcommands or bad arguments.
    """
    if not tokens:
        raise CommandError("usage: git <command>")
    sub = tokens[0].lower()
    args = tokens[1:]

    if sub == "commit":
        return _git_commit(eng, args)
    if sub == "branch":
        return _git_branch(eng, args)
    if sub == "checkout":
        return _git_checkout(eng, args)
    if sub == "switch":
        return _git_switch(eng, args)
    if sub == "merge":
        return _git_merge(eng, args)
    if sub == "rebase":
        return _git_rebase(eng, args)
    if sub == "cherry-pick":
        return _git_cherry_pick(eng, args)
    if sub == "reset":
        return _git_reset(eng, args)
    if sub == "revert":
        return _git_revert(eng, args)
    if sub == "tag":
        return _git_tag(eng, args)
    if sub == "clone":
        return _git_clone(eng, args)
    if sub == "fetch":
        return _git_fetch(eng, args)
    if sub == "pull":
        return _git_pull(eng, args)
    if sub == "push":
        return _git_push(eng, args)
    if sub == "faketeamwork":
        return _git_fake_teamwork(eng, args)
    if sub == "fakecreateremote":
        return _git_fake_create_remote(eng, args)
    if sub in {"log", "status", "help"}:
        return _exec_meta(eng, sub, args, "git " + sub)

    # Aliases used by some LGB solutions.
    if sub == "cherrypick":
        return _git_cherry_pick(eng, args)

    raise CommandError(f"unsupported git command '{sub}'")


def _require_clean_line(eng: GitEngine) -> None:
    """Reject operations that need a clean simulated working tree.

    The structural model is always clean; this exists as a stable hook and for
    future working-dir commands.

    Args:
        eng: Engine (unused).

    Raises:
        GitError: Never in the structural model.
    """
    _ = eng


def _advance_branch_or_detached(eng: GitEngine, commit_id: str, message: str) -> str:
    """Create a commit on HEAD and move the current pointer.

    Args:
        eng: Engine to mutate.
        commit_id: Unused placeholder for symmetry; see add_commit.
        message: Commit message.

    Returns:
        New commit id.
    """
    _ = commit_id
    head = eng.head_commit_id()
    new_id = eng.add_commit([head], message=message)
    if eng.head_detached:
        eng.set_head_commit(new_id)
    else:
        eng.move_branch(eng.head_target, new_id)
    return new_id


def _git_commit(eng: GitEngine, args: list[str]) -> CommandResult:
    """``git commit``.

    Args:
        eng: Engine.
        args: Optional ``-m/--message``.

    Returns:
        Result with the new commit id.

    Raises:
        CommandError: On bad flags.
    """
    message = "Commit"
    i = 0
    while i < len(args):
        if args[i] in {"-m", "--message"} and i + 1 < len(args):
            message = args[i + 1]
            i += 2
            continue
        if args[i].startswith("--message="):
            message = args[i].split("=", 1)[1]
            i += 1
            continue
        if args[i] in {"-a", "--all", "--allow-empty", "--amend"}:
            # Structural model: amend is treated as a normal commit unless
            # --amend is the only semantic that needs history rewrite.
            if args[i] == "--amend":
                return _git_commit_amend(eng)
            i += 1
            continue
        raise CommandError(f"unsupported commit flag '{args[i]}'")
    _require_clean_line(eng)
    if eng.head_detached:
        # LGB allows committing on detached HEAD (new commit, HEAD follows).
        new_id = eng.add_commit([eng.head_commit_id()], message=message)
        eng.set_head_commit(new_id)
        return CommandResult(messages=[f"created commit {new_id}"])
    new_id = _advance_branch_or_detached(eng, eng.head_commit_id(), message)
    return CommandResult(messages=[f"created commit {new_id} on {eng.head_target}"])


def _git_commit_amend(eng: GitEngine) -> CommandResult:
    """Rewrite HEAD commit in place (simplified ``--amend``).

    Args:
        eng: Engine.

    Returns:
        Result noting the amended commit id.

    Raises:
        CommandError: On root commits with no parents (kept as new commit).
    """
    old_id = eng.head_commit_id()
    old = eng.commits[old_id]
    new_id = eng.allocate_commit_id()
    eng.commits[new_id] = type(old)(
        id=new_id,
        parents=list(old.parents),
        message=old.message or "Commit",
        root_commit=old.root_commit,
    )
    if eng.head_detached:
        eng.set_head_commit(new_id)
    else:
        eng.move_branch(eng.head_target, new_id)
    return CommandResult(messages=[f"amended {old_id} -> {new_id}"])


def _git_branch(eng: GitEngine, args: list[str]) -> CommandResult:
    """``git branch`` create / force-move / delete.

    Args:
        eng: Engine.
        args: Branch operands and flags ``-f``, ``-d``, ``-D``.

    Returns:
        Result messages.

    Raises:
        CommandError: On bad usage.
    """
    force = False
    delete = False
    names: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in {"-f", "--force"}:
            force = True
        elif a in {"-d", "-D", "--delete"}:
            delete = True
        elif a in {"-a", "-r", "-l", "--list", "-v", "--verbose", "--show-current"}:
            i += 1
            continue
        elif a.startswith("-"):
            raise CommandError(f"unsupported branch flag '{a}'")
        else:
            names.append(a)
        i += 1

    if delete:
        if not names:
            raise CommandError("usage: git branch -d <name>")
        for name in names:
            if name not in eng.branches:
                raise CommandError(f"branch '{name}' does not exist")
            if not eng.head_detached and eng.head_target == name:
                raise CommandError(f"cannot delete branch '{name}' checked out at HEAD")
            del eng.branches[name]
        return CommandResult(messages=[f"deleted branch {', '.join(names)}"])

    if not names:
        # bare `git branch` lists branches
        lines = [f"* {n} -> {r.target}" if not eng.head_detached and eng.head_target == n else f"  {n} -> {r.target}" for n, r in sorted(eng.branches.items())]
        return CommandResult(messages=lines or ["(no branches)"])

    if len(names) > 2:
        raise CommandError("usage: git branch <name> [<start-point>]")

    name = names[0]
    start = eng.head_commit_id() if len(names) == 1 else eng.resolve_commit(names[1])
    if name in eng.branches and not force:
        raise CommandError(f"branch '{name}' already exists")
    if name.startswith("o/"):
        raise CommandError("cannot create remote-tracking branch with git branch")
    eng.move_branch(name, start)
    return CommandResult(messages=[f"created branch {name} at {start}"])


def _git_checkout(eng: GitEngine, args: list[str]) -> CommandResult:
    """``git checkout``.

    Args:
        eng: Engine.
        args: ``-b name``, ``-``, or a revision.

    Returns:
        Result messages.

    Raises:
        CommandError: On bad usage.
    """
    if not args:
        raise CommandError("usage: git checkout <rev> | -b <name> | -")

    if args[0] in {"-b", "-B"}:
        if len(args) < 2:
            raise CommandError("usage: git checkout -b <name> [<start>]")
        name = args[1]
        start = eng.resolve_commit(args[2]) if len(args) > 2 else eng.head_commit_id()
        if name in eng.branches and args[0] == "-b":
            raise CommandError(f"branch '{name}' already exists")
        eng.move_branch(name, start)
        eng.set_head_branch(name)
        return CommandResult(messages=[f"switched to new branch '{name}'"])

    if args[0] == "--":
        raise CommandError("checkout of paths is not simulated")
    if args[0] == "-":
        return _checkout_previous(eng)

    rev = args[0]
    # Prefer branch name when it exists as a branch.
    if rev in eng.branches:
        eng.set_head_branch(rev)
        return CommandResult(messages=[f"switched to branch '{rev}'"])
    if rev in eng.remote_branches:
        # Detached HEAD at remote branch tip, like git checkout o/main.
        commit_id = eng.remote_branches[rev].target
        eng.set_head_commit(commit_id)
        return CommandResult(messages=[f"detached HEAD at {commit_id} (from {rev})"])
    commit_id = eng.resolve_commit(rev)
    eng.set_head_commit(commit_id)
    return CommandResult(messages=[f"detached HEAD at {commit_id}"])


def _checkout_previous(eng: GitEngine) -> CommandResult:
    """``git checkout -`` using a tiny reflog stored on the engine via attributes.

    Streamlit host keeps a HEAD history stack; this helper only moves to the
    previous target if the engine carries ``_prev_head``.

    Args:
        eng: Engine.

    Returns:
        Result messages.

    Raises:
        CommandError: If no previous HEAD is known.
    """
    prev = getattr(eng, "_prev_head", None)
    if not prev:
        raise CommandError("no previous HEAD location")
    target, detached = prev
    if detached:
        eng.set_head_commit(target)
    else:
        eng.set_head_branch(target)
    return CommandResult(messages=[f"switched to {'commit ' if detached else 'branch '}{target}"])


def _git_switch(eng: GitEngine, args: list[str]) -> CommandResult:
    """``git switch`` mapped onto checkout semantics.

    Args:
        eng: Engine.
        args: Switch arguments.

    Returns:
        Result messages.
    """
    return _git_checkout(eng, args)


def _git_merge(eng: GitEngine, args: list[str]) -> CommandResult:
    """``git merge <rev>``.

    Args:
        eng: Engine.
        args: One revision, optional ``--no-ff`` / ``-m``.

    Returns:
        Result messages.

    Raises:
        CommandError: On bad usage or up-to-date / already-up-to-date cases
        that LGB surfaces as messages rather than errors.
    """
    message = "Merge commit"
    rev = None
    for a in args:
        if a in {"--no-ff", "--ff", "--no-edit", "--edit"}:
            continue
        if a in {"-m", "--message"}:
            continue
        if a.startswith("-"):
            raise CommandError(f"unsupported merge flag '{a}'")
        rev = a
    if rev is None:
        raise CommandError("usage: git merge <branch>")

    target = eng.resolve_commit(rev)
    current = eng.head_commit_id()

    if target == current:
        return CommandResult(messages=["Already up to date."])
    if eng.is_ancestor(target, current):
        return CommandResult(messages=["Already up to date."])
    if eng.is_ancestor(current, target):
        # Fast-forward
        if eng.head_detached:
            eng.set_head_commit(target)
        else:
            eng.move_branch(eng.head_target, target)
        return CommandResult(messages=[f"Fast-forward to {target}"])

    new_id = eng.add_commit([current, target], message=message)
    if eng.head_detached:
        eng.set_head_commit(new_id)
    else:
        eng.move_branch(eng.head_target, new_id)
    return CommandResult(messages=[f"Merge made by 'ort' strategy -> {new_id}"])


def _git_rebase(eng: GitEngine, args: list[str]) -> CommandResult:
    """``git rebase`` including ``--onto``.

    Args:
        eng: Engine.
        args: ``<upstream>`` or ``--onto <newbase> <oldbase> [<branch>]``.

    Returns:
        Result messages.

    Raises:
        CommandError: On bad usage or empty rebase.
    """
    if not args:
        raise CommandError("usage: git rebase <upstream> | --onto <to> <from> [<branch>]")

    if args[0] == "--onto":
        if len(args) < 3:
            raise CommandError("usage: git rebase --onto <newbase> <oldbase> [<branch>]")
        newbase = eng.resolve_commit(args[1])
        oldbase = eng.resolve_commit(args[2])
        if len(args) >= 4:
            branch_name = args[3]
            if branch_name not in eng.branches:
                raise CommandError(f"branch '{branch_name}' does not exist")
            source_tip = eng.branches[branch_name].target
        else:
            branch_name = None
            source_tip = eng.head_commit_id()
        commits = _commits_to_replay(eng, source_tip, oldbase)
        new_tip = _replay_commits(eng, commits, newbase)
        if branch_name:
            eng.move_branch(branch_name, new_tip)
            if not eng.head_detached and eng.head_target == branch_name:
                pass
            return CommandResult(messages=[f"rebased {branch_name} onto {newbase} -> {new_tip}"])
        if eng.head_detached:
            eng.set_head_commit(new_tip)
        else:
            eng.move_branch(eng.head_target, new_tip)
        return CommandResult(messages=[f"rebased onto {newbase} -> {new_tip}"])

    upstream_name = args[0]
    upstream = eng.resolve_commit(upstream_name)
    current = eng.head_commit_id()
    if upstream == current:
        return CommandResult(messages=["Current branch is up to date."])
    if eng.is_ancestor(upstream, current):
        commits = _commits_to_replay(eng, current, upstream)
    elif eng.is_ancestor(current, upstream):
        # Current is strictly behind upstream — rebasing is a fast-forward move.
        if eng.head_detached:
            eng.set_head_commit(upstream)
        else:
            eng.move_branch(eng.head_target, upstream)
        return CommandResult(messages=[f"rebased {eng.head_target} onto {upstream_name} -> {upstream}"])
    else:
        commits = _commits_to_replay(eng, current, eng.merge_base(current, upstream))

    if not commits:
        return CommandResult(messages=["Current branch is up to date."])

    new_tip = _replay_commits(eng, commits, upstream)
    if eng.head_detached:
        eng.set_head_commit(new_tip)
    else:
        eng.move_branch(eng.head_target, new_tip)
    return CommandResult(messages=[f"rebased {eng.head_target} onto {upstream_name} -> {new_tip}"])


def _commits_to_replay(eng: GitEngine, tip: str, below: str | None) -> list[str]:
    """List commits on ``tip`` that are not reachable from ``below``, oldest first.

    Args:
        eng: Engine.
        tip: Source tip.
        below: Exclusion root (exclusive). If None, only ``tip`` is used.

    Returns:
        Commit ids oldest-first.
    """
    reachable: set[str] = set()
    if below is not None:
        reachable = set(eng.commits_inclusive_history(below))

    chain: list[str] = []
    current = tip
    while current and current not in reachable:
        chain.append(current)
        commit = eng.commits[current]
        if not commit.parents:
            break
        current = commit.parents[0]
    chain.reverse()
    return chain


def _replay_commits(eng: GitEngine, commits: list[str], newbase: str) -> str:
    """Copy commits onto ``newbase``, creating new commit objects.

    Args:
        eng: Engine.
        commits: Commits oldest-first to copy.
        newbase: New base commit id.

    Returns:
        New tip commit id (or ``newbase`` when empty).
    """
    mapping: dict[str, str] = {}
    parent = newbase
    for old_id in commits:
        old = eng.commits[old_id]
        new_parents = [mapping.get(p, p) if p in mapping or p in {c for c in commits} else parent for p in old.parents[:1] or [parent]]
        # For linear replay use first parent chain only; merges are flattened to single-parent copies.
        if not new_parents:
            new_parents = [parent]
        new_id = eng.add_commit([parent], message=old.message or f"rebase of {old_id}")
        mapping[old_id] = new_id
        parent = new_id
    return parent


def _git_cherry_pick(eng: GitEngine, args: list[str]) -> CommandResult:
    """``git cherry-pick <rev...>``.

    Args:
        eng: Engine.
        args: One or more revisions.

    Returns:
        Result messages.

    Raises:
        CommandError: On empty args.
    """
    if not args:
        raise CommandError("usage: git cherry-pick <rev...>")
    created: list[str] = []
    for rev in args:
        source = eng.resolve_commit(rev)
        src = eng.commits[source]
        head = eng.head_commit_id()
        if eng.is_ancestor(source, head) or eng.is_ancestor(head, source):
            # Still copy as a new commit like LGB visualization does for cherry-pick demos.
            pass
        new_id = eng.add_commit([head], message=src.message or f"cherry-pick {source}")
        created.append(new_id)
        if eng.head_detached:
            eng.set_head_commit(new_id)
        else:
            eng.move_branch(eng.head_target, new_id)
    return CommandResult(messages=[f"cherry-picked {', '.join(created)}"])


def _git_reset(eng: GitEngine, args: list[str]) -> CommandResult:
    """``git reset --hard <rev>``.

    Args:
        eng: Engine.
        args: Flags and optional revision (defaults to HEAD).

    Returns:
        Result messages.

    Raises:
        CommandError: On non-hard reset modes (not simulated).
    """
    if args and args[0] in {"--soft", "--mixed", "--keep"}:
        raise CommandError("only `git reset --hard` is simulated")
    rev = None
    for a in args:
        if a in {"--hard", "--hard="}:
            continue
        if a.startswith("-"):
            raise CommandError(f"unsupported reset flag '{a}'")
        rev = a
    target = eng.resolve_commit(rev) if rev else eng.head_commit_id()
    if eng.head_detached:
        eng.set_head_commit(target)
    else:
        eng.move_branch(eng.head_target, target)
    return CommandResult(messages=[f"reset {eng.head_target} to {target}"])


def _git_revert(eng: GitEngine, args: list[str]) -> CommandResult:
    """``git revert <rev>`` — add a commit whose message notes the revert.

    Args:
        eng: Engine.
        args: One revision.

    Returns:
        Result messages.

    Raises:
        CommandError: On bad usage.
    """
    if not args:
        raise CommandError("usage: git revert <rev>")
    source = eng.resolve_commit(args[0])
    head = eng.head_commit_id()
    new_id = eng.add_commit([head], message=f'Revert "{source}"')
    if eng.head_detached:
        eng.set_head_commit(new_id)
    else:
        eng.move_branch(eng.head_target, new_id)
    return CommandResult(messages=[f"reverted {source} -> {new_id}"])


def _git_tag(eng: GitEngine, args: list[str]) -> CommandResult:
    """``git tag <name> [<rev>]``.

    Args:
        eng: Engine.
        args: Tag name and optional revision.

    Returns:
        Result messages.

    Raises:
        CommandError: On bad usage.
    """
    if not args:
        lines = [f"{n} -> {r.target}" for n, r in sorted(eng.tags.items())]
        return CommandResult(messages=lines or ["(no tags)"])
    if args[0] in {"-d", "-D", "--delete"}:
        for name in args[1:]:
            eng.tags.pop(name, None)
        return CommandResult(messages=["deleted tags"])
    name = args[0]
    target = eng.resolve_commit(args[1]) if len(args) > 1 else eng.head_commit_id()
    eng.tags[name] = Ref(id=name, target=target, kind="tag")
    return CommandResult(messages=[f"created tag {name} at {target}"])


def _git_clone(eng: GitEngine, args: list[str]) -> CommandResult:
    """``git clone`` — create a simulated remote and remote-tracking branches.

    Args:
        eng: Engine.
        args: Optional remote URL (ignored beyond display).

    Returns:
        Result messages.

    Raises:
        CommandError: If a remote already exists.
    """
    _ = args
    if eng.remote_exists:
        raise CommandError("remote already exists")
    eng.remote_exists = True
    eng.remote_url = "origin"
    for name, ref in list(eng.branches.items()):
        eng.remote_branches[f"o/{name}"] = Ref(id=f"o/{name}", target=ref.target, kind="remote")
    return CommandResult(messages=["cloned from origin (simulated)"])


def _git_fake_create_remote(eng: GitEngine, args: list[str]) -> CommandResult:
    """``git fakeCreateRemote`` — LGB helper for remote levels.

    Args:
        eng: Engine.
        args: Unused.

    Returns:
        Result messages.
    """
    _ = args
    return _git_clone(eng, [])


def _ensure_remote(eng: GitEngine) -> None:
    """Create a remote if missing (fetch/push convenience).

    Args:
        eng: Engine to mutate.
    """
    if not eng.remote_exists:
        eng.remote_exists = True
        eng.remote_url = "origin"


def _remote_name(local: str) -> str:
    """Map a local branch name to its remote-tracking name.

    Args:
        local: Branch name.

    Returns:
        ``o/``-prefixed name.
    """
    return local if local.startswith("o/") else f"o/{local}"


def _git_fetch(eng: GitEngine, args: list[str]) -> CommandResult:
    """``git fetch`` — remote branches already represent the remote.

    In this simulation the remote-tracking refs are the source of truth for the
    remote, so fetch is a no-op success (kept for pedagogy / level checks).

    Args:
        eng: Engine.
        args: Unused.

    Returns:
        Result messages.
    """
    _ = args
    _ensure_remote(eng)
    return CommandResult(messages=["fetched from origin (simulated)"])


def _git_pull(eng: GitEngine, args: list[str]) -> CommandResult:
    """``git pull`` / ``git pull --rebase``.

    Args:
        eng: Engine.
        args: Flags and optional remote/branch.

    Returns:
        Result messages.

    Raises:
        CommandError: On bad usage.
    """
    use_rebase = False
    for a in args:
        if a == "--rebase":
            use_rebase = True
        elif a in {"--ff-only", "--no-rebase", "--ff"}:
            continue
        elif a.startswith("-"):
            raise CommandError(f"unsupported pull flag '{a}'")
    _ensure_remote(eng)
    # Determine local branch and remote counterpart.
    if eng.head_detached:
        raise CommandError("cannot pull with detached HEAD in this simulation")
    local = eng.head_target
    remote = _remote_name(local)
    if remote not in eng.remote_branches:
        # Pull from o/main when current tracking is missing.
        remote = "o/main" if "o/main" in eng.remote_branches else remote
    if remote not in eng.remote_branches:
        return CommandResult(messages=["There is no tracking information for the current branch."])

    remote_tip = eng.remote_branches[remote].target
    local_tip = eng.branches[local].target
    if eng.is_ancestor(remote_tip, local_tip):
        return CommandResult(messages=["Already up to date."])
    if use_rebase:
        commits = _commits_to_replay(eng, local_tip, eng.merge_base(local_tip, remote_tip))
        new_tip = _replay_commits(eng, commits, remote_tip) if commits else remote_tip
        eng.move_branch(local, new_tip)
        return CommandResult(messages=[f"pulled --rebase from {remote} -> {new_tip}"])
    if eng.is_ancestor(local_tip, remote_tip):
        eng.move_branch(local, remote_tip)
        return CommandResult(messages=[f"Fast-forward to {remote_tip}"])
    new_id = eng.add_commit([local_tip, remote_tip], message="Merge remote-tracking branch")
    eng.move_branch(local, new_id)
    return CommandResult(messages=[f"pulled (merge) from {remote} -> {new_id}"])


def _git_push(eng: GitEngine, args: list[str]) -> CommandResult:
    """``git push`` / ``git push origin <branch>``.

    Args:
        eng: Engine.
        args: Optional remote and refspec.

    Returns:
        Result messages.

    Raises:
        CommandError: When push would be non-fast-forward (remote ahead).
    """
    _ensure_remote(eng)
    local: str | None = None
    for a in args:
        if a in {"origin", "-u", "--set-upstream"} or a.startswith("-"):
            continue
        local = a
    if local is None:
        if eng.head_detached:
            raise CommandError("cannot push with detached HEAD; pass a branch name")
        local = eng.head_target

    if local not in eng.branches:
        raise CommandError(f"branch '{local}' does not exist")

    remote = _remote_name(local)
    local_tip = eng.branches[local].target
    if remote in eng.remote_branches:
        remote_tip = eng.remote_branches[remote].target
        if remote_tip == local_tip:
            return CommandResult(messages=["Everything up-to-date"])
        if not eng.is_ancestor(remote_tip, local_tip):
            raise CommandError(f"push rejected: non-fast-forward on {remote}")
    eng.remote_branches[remote] = Ref(id=remote, target=local_tip, kind="remote")
    return CommandResult(messages=[f"pushed {local} -> {remote} ({local_tip})"])


def _git_fake_teamwork(eng: GitEngine, args: list[str]) -> CommandResult:
    """``git fakeTeamwork [branch] [n]`` — teammate commits on a remote branch.

    Args:
        eng: Engine.
        args: Optional branch name (local name or ``o/branch``) and commit count.

    Returns:
        Result messages.

    Raises:
        CommandError: When the remote does not exist.
    """
    if not eng.remote_exists and not eng.remote_branches:
        raise CommandError("no remote configured; run `git clone` or `git fakeCreateRemote` first")
    if not eng.remote_exists:
        eng.remote_exists = True
        eng.remote_url = eng.remote_url or "origin"
    branch = args[0] if args else (eng.head_target if not eng.head_detached else "main")
    count = 1
    if len(args) >= 2:
        try:
            count = max(1, int(args[1]))
        except ValueError as exc:
            raise CommandError("usage: git fakeTeamwork [branch] [count]") from exc
    if branch.startswith("o/"):
        remote_branch = branch
    else:
        remote_branch = _remote_name(branch)
    if remote_branch not in eng.remote_branches:
        # bootstrap remote branch at current local tip or root
        if branch in eng.branches:
            eng.remote_branches[remote_branch] = Ref(
                id=remote_branch, target=eng.branches[branch].target, kind="remote"
            )
        elif eng.commits:
            first = next(iter(eng.commits))
            eng.remote_branches[remote_branch] = Ref(
                id=remote_branch, target=first, kind="remote"
            )
        else:
            raise CommandError(f"remote branch '{remote_branch}' does not exist")

    tip = eng.remote_branches[remote_branch].target
    created = []
    for i in range(count):
        new_id = eng.add_commit([tip], message=f"teammate commit {i + 1}")
        created.append(new_id)
        tip = new_id
    eng.remote_branches[remote_branch] = Ref(id=remote_branch, target=tip, kind="remote")
    return CommandResult(messages=[f"teammate pushed {', '.join(created)} to {remote_branch}"])
