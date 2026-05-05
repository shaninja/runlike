#!/usr/bin/env python

import click

try:
    from .inspector import Inspector
    from .option_warnings import UnsupportedOptionWarningEngine
except ValueError:
    from inspector import Inspector
    from option_warnings import UnsupportedOptionWarningEngine


def emit_unsupported_warnings(inspector, input_path, rendered_command):
    for line in UnsupportedOptionWarningEngine().warning_lines(
            inspector.facts,
            input_path,
            image_facts=inspector.image_facts,
            rendered_command=rendered_command):
        click.echo(line, err=True)


@click.command(
    help="Shows command line necessary to run copy of existing Docker container.")
@click.argument("container", required=False )
@click.option(
    "--no-name",
    is_flag=True,
    help="Do not include container name in output")
@click.option("-p", "--pretty", is_flag=True)
@click.option("-s", "--stdin", is_flag=True)
def cli(container, no_name, pretty, stdin):

    # TODO: -i, -t, -d as added options that override the inspection
    if container:
        ins = Inspector(container, no_name, pretty)
        ins.inspect()
        rendered_command = ins.format_cli()
        emit_unsupported_warnings(ins, "container_name", rendered_command)
        print(rendered_command)
    elif stdin:
        ins = Inspector()
        ins.pretty = pretty
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
