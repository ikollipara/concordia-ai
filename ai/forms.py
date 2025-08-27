"""
Project:     Concordia AI
Name:        ai/forms.py
Author:      Ian Kollipara <ian.kollipara@cune.edu>
Date:        2025-08-14
Description: Forms for Concordia AI
"""

from django import forms

from ai import models


class LoginForm(forms.Form):
    """Login Form.

    The body is empty since we just use it to verify
    CSRF stuff.
    """


class PromptForm(forms.ModelForm):
    """PromptForm.

    This is the form used for validationa and creation of a prompt.
    """

    def __init__(self, bot: models.CourseBot, request, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.bot = bot
        self.instance.user = request.user

    class Meta:
        model = models.Prompt
        fields = ["body"]
