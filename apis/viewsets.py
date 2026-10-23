from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from apis.permissions import IsOwnerOrAdmin


class ActorMixin:
    def get_actor_user(self):
        request = self.request
        if request.user and request.user.is_authenticated:
            return request.user

        if not getattr(settings, "DEV_AUTH_BYPASS", False):
            raise NotAuthenticated("Authentication credentials were not provided.")

        User = get_user_model()
        email = getattr(settings, "DEV_AUTH_BYPASS_EMAIL", "chatbot-dev@local.test")
        dev_user, _ = User.objects.get_or_create(
            email=email,
            defaults={"full_name": "Chatbot Dev", "is_active": True},
        )
        return dev_user


def get_permission_classes():
    if getattr(settings, "DEV_AUTH_BYPASS", False):
        return [AllowAny]
    return [IsAuthenticated]


class BaseModelViewSet(ModelViewSet):
    permission_classes = get_permission_classes()


_WRITE_ACTIONS = ("create", "update", "partial_update", "destroy")


class StaffWriteViewSet(BaseModelViewSet):
    """Reference data (catalog, plans, achievements): any signed-in user may read it, only staff
    may change it. These used to accept writes from every student."""

    def get_permissions(self):
        if getattr(settings, "DEV_AUTH_BYPASS", False):
            return [AllowAny()]
        if self.action in _WRITE_ACTIONS:
            return [IsAdminUser()]
        return [IsAuthenticated()]


class SystemOwnedMixin:
    """Rows that belong to a user but are written by the system (mastery, streaks, attempts,
    subscriptions, achievements...). The owner may read them; changing them is staff-only, so a
    student cannot award themselves an achievement, upgrade a plan or edit their own score.
    Set `owner_may_delete = True` where deleting your own row is a feature (a signed-in device)."""

    owner_may_delete = False

    def get_permissions(self):
        if getattr(settings, "DEV_AUTH_BYPASS", False):
            return [AllowAny()]
        if self.action == "destroy" and self.owner_may_delete:
            return [IsAuthenticated(), IsOwnerOrAdmin()]
        if self.action in _WRITE_ACTIONS:
            return [IsAdminUser()]
        return [IsAuthenticated()]


class UserScopedViewSet(ActorMixin, BaseModelViewSet):
    owner_field = "user"

    def get_permissions(self):
        if getattr(settings, "DEV_AUTH_BYPASS", False):
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
        actor = self.get_actor_user()
        # Only staff may create a row in someone else's name; for everyone else the owner is the caller,
        # whatever the request body says.
        if actor.is_staff and self.owner_field in serializer.validated_data:
            serializer.save()
        else:
            serializer.save(**{self.owner_field: actor})


class UserPrimaryKeyViewSet(UserScopedViewSet):
    """For models where user is the primary key (OneToOne)."""

    def get_object(self):
        if self.kwargs.get(self.lookup_field) == "me":
            self.kwargs[self.lookup_field] = str(self.get_actor_user().id)
        return super().get_object()

    def perform_create(self, serializer):
        user = self.get_actor_user()
        model_class = serializer.Meta.model
        user_field = model_class._meta.get_field("user")
        if user_field.primary_key:
            defaults = {
                key: value
                for key, value in serializer.validated_data.items()
                if key != "user"
            }
            instance, _ = model_class.objects.update_or_create(user=user, defaults=defaults)
            serializer.instance = instance
            return
        serializer.save(user=user)
