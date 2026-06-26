from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from apis.permissions import IsOwnerOrAdmin


class ActorMixin:
    def get_actor_user(self):
        request = self.request
        if request.user and request.user.is_authenticated:
            return request.user

        if not getattr(settings, "CHATBOT_AUTH_DISABLED", False):
            raise NotAuthenticated("Authentication credentials were not provided.")

        User = get_user_model()
        email = getattr(settings, "CHATBOT_DEV_EMAIL", "chatbot-dev@local.test")
        dev_user, _ = User.objects.get_or_create(
            email=email,
            defaults={"full_name": "Chatbot Dev", "is_active": True},
        )
        return dev_user


def get_permission_classes():
    if getattr(settings, "CHATBOT_AUTH_DISABLED", False):
        return [AllowAny]
    return [IsAuthenticated]


class BaseModelViewSet(ModelViewSet):
    permission_classes = get_permission_classes()


class UserScopedViewSet(ActorMixin, BaseModelViewSet):
    owner_field = "user"

    def get_permissions(self):
        if getattr(settings, "CHATBOT_AUTH_DISABLED", False):
            return [AllowAny()]
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsOwnerOrAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.get_actor_user()
        if user.is_staff:
            return queryset
        return queryset.filter(**{self.owner_field: user})

    def perform_create(self, serializer):
        if self.owner_field in serializer.validated_data:
            serializer.save()
        else:
            serializer.save(**{self.owner_field: self.get_actor_user()})


class UserPrimaryKeyViewSet(UserScopedViewSet):
    """For models where user is the primary key (OneToOne)."""

    def get_object(self):
        if self.kwargs.get(self.lookup_field) == "me":
            self.kwargs[self.lookup_field] = str(self.get_actor_user().id)
        return super().get_object()
