from slack_bolt.adapter.django import SlackRequestHandler

from .factory import build_bolt_app

slack_handler: SlackRequestHandler = build_bolt_app()
