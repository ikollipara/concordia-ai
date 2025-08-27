"""
Project:     Concordia AI
Name:        ai/views.py
Author:      Ian Kollipara <ian.kollipara@cune.edu>
Date:        2025-08-14
Description: The views for the Concordia AI project
"""

import json

from django import conf, http, shortcuts, urls
from django.contrib.auth import decorators as auth_decorators
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth import mixins as auth_mixins
from django.core import serializers
from django.utils import decorators
from django.views import generic
from django.views.decorators import csrf as csrf_decorators
from django.views.decorators import http as http_decorators
from onelogin.saml2 import auth, constants, idp_metadata_parser, settings, utils

from ai import forms, models

UserModel = get_user_model()

### Mixins ###


class SAMLMixin:
    """
    SAMLMixin.

    A mixin to provide useful utilities for SAML Views.
    """

    timeout = 60 * 4  # 4 Minutes

    @property
    def metadata_url(self) -> str:
        return conf.settings.METADATA_URL

    def prepare_request(self):
        """Prepare a SAML Request from Django's request."""
        result = {
            "https": "on" if self.request.is_secure() else "off",
            "http_host": self.request.META["HTTP_HOST"],
            "script_name": self.request.META["PATH_INFO"],
            "get_data": self.request.GET.copy(),
            # Uncomment if using ADFS as IdP, https://github.com/onelogin/python-saml/pull/144
            # 'lowercase_urlencoding': True,
            "post_data": self.request.POST.copy(),
        }
        return result

    def build_saml_config(self):
        """Build a valid SAML Configuration."""

        idp_data = idp_metadata_parser.OneLogin_Saml2_IdPMetadataParser.parse_remote(
            self.metadata_url, timeout=self.timeout
        )

        config = {
            "debug": conf.settings.DEBUG,
            "sp": {
                "entityId": self.request.build_absolute_uri(
                    urls.reverse_lazy("ai:saml_metadata")
                ),
                "assertionConsumerService": {
                    "url": self.request.build_absolute_uri(
                        urls.reverse_lazy("ai:saml_acs")
                    ),
                    "binding": constants.OneLogin_Saml2_Constants.BINDING_HTTP_POST,
                },
                "singleLogoutService": {
                    "url": self.request.build_absolute_uri(
                        urls.reverse_lazy("ai:saml_sls")
                    ),
                    "binding": constants.OneLogin_Saml2_Constants.BINDING_HTTP_REDIRECT,
                },
            },
            "security": {
                "logoutRequestSigned": False,
                "logoutResponseSigned": False,
            },
        } | idp_data

        print(config)

        return config

    def init_auth(self):
        """Initialize the SAML Auth Provider."""

        req = self.prepare_request()
        config = self.build_saml_config()

        return auth.OneLogin_Saml2_Auth(req, config)


### SAML Views ###


class SAMLMetadataView(SAMLMixin, generic.View):
    """SAML Metadata URL."""

    http_method_names = ["get", "head", "options"]

    def get(self, request):
        config = self.build_saml_config()

        saml_settings = settings.OneLogin_Saml2_Settings(
            settings=config, sp_validation_only=True
        )
        metadata = saml_settings.get_sp_metadata()
        errors = saml_settings.validate_metadata(metadata)

        if len(errors) > 0:
            response = http.HttpResponseServerError(content={"errors": errors})
            response.headers["Content-Type"] = "application/json"
            return response

        response = http.HttpResponse(content=metadata)
        response.headers["Content-Type"] = "text/xml"
        return response


@decorators.method_decorator(csrf_decorators.csrf_exempt, name="dispatch")
class SAMLAcsView(SAMLMixin, generic.View):
    """SAML ACS View."""

    REQUEST_ID_PARAM = "AuthNRequestID"

    http_method_names = ["post", "get", "head", "options"]

    def post(self, request):
        errors = []
        error_reason = None

        _auth = self.init_auth()
        request_id = self.request.session.get(self.REQUEST_ID_PARAM, default=None)

        try:
            _auth.process_response(request_id)

        except auth.OneLogin_Saml2_Error as e:
            errors = ["error"]
            error_reason = str(e)
            if not errors:
                errors = _auth.get_errors()

        if errors:
            error_reason = _auth.get_last_error_reason() or error_reason
            response = shortcuts.render(
                self.request,
                "ai/saml_error.html",
                {"errors": errors, "reason": error_reason},
            )
            response.status_code = 500
            return response

        email = _auth.get_nameid()

        first_name = _auth.get_attribute(
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname"
        )
        last_name = _auth.get_attribute(
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname"
        )

        if user := UserModel.objects.get(username=email):
            login(self.request, user)
        else:
            user = UserModel.objects.create_user(
                email=email,
                username=email,
                first_name=first_name[0],
                last_name=last_name[0],
                password="Nothing",
            )

            login(self.request, user)

        return shortcuts.redirect(conf.settings.REDIRECT_URL)

    get = post


@decorators.method_decorator(csrf_decorators.csrf_exempt, name="dispatch")
class SAMLSlsView(SAMLMixin, generic.View):
    """SAML SLS View."""

    http_method_names = ["get", "post", "head", "options"]

    REQUEST_ID_PARAM = "LogoutRequestID"

    def post(self, request):
        _auth = self.init_auth()
        return shortcuts.redirect(_auth.logout(urls.reverse("ai:saml_sls")))

    def get(self, request):
        _auth = self.init_auth()
        request_id = self.request.session.get(self.REQUEST_ID_PARAM, default=None)

        def force_logout():
            """SAML Callback."""

            logout(self.request)

        redirect_to = None
        error_reason = None

        try:
            redirect_to = _auth.process_slo(
                request_id=request_id,
                delete_session_cb=force_logout,
                keep_local_session=not self.request.user.is_authenticated,
            )
        except auth.OneLogin_Saml2_Error as e:
            error_reason = str(e)
        errors = _auth.get_errors()

        if errors:
            error_reason = _auth.get_last_error_reason() or error_reason

            response = http.HttpResponseBadRequest(content=error_reason)
            response.headers["Content-Type"] = "text/plain"
            return response

        redirect_to = redirect_to or urls.reverse_lazy("ai:saml_login")
        return shortcuts.redirect(redirect_to)


class SAMLLoginView(SAMLMixin, generic.FormView):
    """SAML Login View"""

    form_class = forms.LoginForm
    template_name = "ai/saml_login.html"

    def form_valid(self, form: forms.LoginForm):
        _auth = self.init_auth()

        return shortcuts.redirect(_auth.login())


### AI Views ###


class ApplicationTemplateView(auth_mixins.LoginRequiredMixin, generic.TemplateView):
    """The Wrapping Application View.

    This view contains many holes that are filled by other parts of the UI.
    """

    template_name = "ai/application.html"


class CourseBotListView(auth_mixins.LoginRequiredMixin, generic.ListView):
    """CourseBot List View.

    This view contains the code necessary to display the list of bots available
    to the user.
    """

    model = models.CourseBot
    template_name = "ai/coursebot_list.html"
    context_object_name = "bots"

    def get_queryset(self, *args, **kwargs):
        return models.CourseBot.objects.for_user(self.request.user)


class CourseBotChatView(
    auth_mixins.LoginRequiredMixin, auth_mixins.UserPassesTestMixin, generic.DetailView
):
    """CourseBot Chat View.

    This view contains the code used to display the chat interface. It initializes an Elm
    app that controls the chat interface.
    """

    model = models.CourseBot
    template_name = "ai/coursebot_chat.html"
    context_object_name = "bot"

    def test_func(self):
        return self.get_object().group.user_set.contains(self.request.user)


### AI API Views ###


@auth_decorators.login_required
def coursebot_chat_history_api_view(request: http.HttpRequest, pk: int):
    user = request.user
    course_bot: models.CourseBot = shortcuts.get_object_or_404(models.CourseBot, pk=pk)

    if not course_bot.group.user_set.contains(user):
        response = http.HttpResponse(content={"error": "User cannot view this bot."})
        response.headers["Content-Type"] = "application/json"
        response.status_code = 401
        return response

    qs = models.Prompt.objects.for_bot(course_bot).for_user(user).with_response()

    data = {
        prompt.pk: {
                "id": prompt.pk,
                "body": prompt.body,
                "createdAt": int(prompt.created_at.timestamp() * 1000),
                "response": {"body": prompt.response.body} if prompt.response else None,
            }
        for prompt in qs
    }
    print(data)
    response = http.HttpResponse(content=json.dumps(data))
    response.headers["Content-Type"] = "application/json"
    response.status_code = 200
    print(response)
    return response


@auth_decorators.login_required
@http_decorators.require_POST
def coursebot_prompt_create_view(request: http.HttpRequest, pk: int):
    user = request.user
    course_bot: models.CourseBot = shortcuts.get_object_or_404(models.CourseBot, pk=pk)

    if not course_bot.group.user_set.contains(user):
        response = http.HttpResponse(content={"error": "User cannot view this bot."})
        response.headers["Content-Type"] = "application/json"
        response.status_code = 401
        return response

    form = forms.PromptForm(course_bot, request, json.loads(request.body))

    prompt: models.Prompt = form.save()

    response = http.HttpResponse(
        json.dumps(
            {
                "id": prompt.pk,
                "body": prompt.body,
                "createdAt": int(prompt.created_at.timestamp() * 1000),
                "response": None
            }
        )
    )
    response.headers["Content-Type"] = "application/json"
    response.status_code = 201
    return response


@auth_decorators.login_required
@http_decorators.require_POST
def coursebot_prompt_response_create_view(
    request: http.HttpRequest, pk: int, prompt_pk: int
):
    user = request.user
    course_bot: models.CourseBot = shortcuts.get_object_or_404(models.CourseBot, pk=pk)
    prompt: models.Prompt = shortcuts.get_object_or_404(models.Prompt, pk=prompt_pk)

    if not course_bot.group.user_set.contains(user):
        response = http.HttpResponse(content={"error": "User cannot view this bot."})
        response.headers["Content-Type"] = "application/json"
        response.status_code = 401
        return response

    response = http.StreamingHttpResponse(
        streaming_content=models.Response.objects.generate(course_bot, prompt)
    )
    response.headers["Content-Type"] = "text/plain"
    return response
