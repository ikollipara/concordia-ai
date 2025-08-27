"""
Project:     Concordia AI
Name:        ai/urls.py
Author:      Ian Kollipara <ian.kollipara@cune.edu>
Date:        2025-08-14
Description: Urls for Concordia AI
"""

from django import urls

from ai import views

app_name = "ai"

urlpatterns = [
    urls.path(
        "accounts/saml/cune/login/", views.SAMLLoginView.as_view(), name="saml_login"
    ),
    urls.path(
        "accounts/saml/cune/metadata/",
        views.SAMLMetadataView.as_view(),
        name="saml_metadata",
    ),
    urls.path("accounts/saml/cune/sls/", views.SAMLSlsView.as_view(), name="saml_sls"),
    urls.path("accounts/saml/cune/acs/", views.SAMLAcsView.as_view(), name="saml_acs"),
    urls.path("", views.ApplicationTemplateView.as_view(), name="application"),
    urls.path("bots/", views.CourseBotListView.as_view(), name="bot_list"),
    urls.path(
        "bots/<int:pk>/chat/", views.CourseBotChatView.as_view(), name="bot_chat"
    ),
    urls.path(
        "api/bots/<int:pk>/prompts/",
        views.coursebot_prompt_create_view,
        name="api_bot_prompt_create",
    ),
    urls.path(
        "api/bots/<int:pk>/history/",
        views.coursebot_chat_history_api_view,
        name="api_bot_history",
    ),
    urls.path(
        "api/bots/<int:pk>/prompts/<int:prompt_pk>/response/",
        views.coursebot_prompt_response_create_view,
        name="api_bot_prompt_response_create",
    ),
]
