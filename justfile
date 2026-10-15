# clips — one recording in, short clips out. `just run <file>` does everything.
set positional-arguments

input := env_var_or_default("INPUT", "")

default:
    @just --list

# Everything: transcribe → select → render → captions
run input *args:
    uv run clips run "$1" "${@:2}"

transcribe input *args:
    uv run clips transcribe "$1" "${@:2}"

select input *args:
    uv run clips select "$1" "${@:2}"

render input *args:
    uv run clips render "$1" "${@:2}"

captions input *args:
    uv run clips captions "$1" "${@:2}"

test:
    uv run ruff check . && uv run ruff format --check . && uv run pytest --cov

setup:
    uv sync --all-groups
