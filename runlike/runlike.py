#!/usr/bin/env python

import click

try:
    from .inspector import Inspector
    from .option_warnings import UnsupportedOptionWarningEngine
except ValueError:
    from inspector import Inspector
    from option_warnings import UnsupportedOptionWarningEngine


def emit_unsupported_warnings(inspector, input_path, rendered_command):
    ignored_option_ids = set()
    if inspector.no_name:
        ignored_option_ids.add("name")
    if inspector.no_labels:
        ignored_option_ids.add("label")
    for line in UnsupportedOptionWarningEngine().warning_lines(
            inspector.facts,
            input_path,
            image_facts=inspector.image_facts,
            rendered_command=rendered_command,
            ignored_option_ids=ignored_option_ids):
        click.echo(line, err=True)


@click.command(
    help="Shows command line necessary to run copy of existing Docker container.")
@click.argument("container", required=False )
@click.option(
    "--no-name",
    is_flag=True,
    help="Do not include container name in output")
@click.option(
    "--use-volume-id",
    is_flag=True,
    help="Keep the automatically assigned volume id")
@click.option("-p", "--pretty", is_flag=True)
@click.option("-s", "--stdin", is_flag=True)
@click.option(
    "-l",
    "--no-labels",
    is_flag=True,
    help="Do not include labels in output")
def cli(container, no_name, use_volume_id, pretty, stdin, no_labels):

    # TODO: -i, -t, -d as added options that override the inspection
    if container:
        ins = Inspector(
            container,
            no_name=no_name,
            pretty=pretty,
            use_volume_id=use_volume_id,
            no_labels=no_labels)
        ins.inspect()
        rendered_command = ins.format_cli()
        emit_unsupported_warnings(ins, "container_name", rendered_command)
        print(rendered_command)
    elif stdin:
        ins = Inspector(
            no_name=no_name,
            pretty=pretty,
            use_volume_id=use_volume_id,
            no_labels=no_labels)
        raw_json = click.get_text_stream('stdin').read()
        ins.set_facts(raw_json)
        rendered_command = ins.format_cli()
        emit_unsupported_warnings(ins, "stdin", rendered_command)
        print(rendered_command)
    else:
        raise click.UsageError("usage error")

def main():
    cli()

if __name__ == "__main__":
    main()
