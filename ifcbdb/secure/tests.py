from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from waffle.testutils import override_switch

from api.models import ApiKey
from api.scopes import BIN_READ, BIN_SYNC


@override_switch("DashboardApi", active=True)
class ApiKeyManagementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("regular", password="pw")
        self.admin = User.objects.create_user(
            "admin", password="pw", is_superuser=True
        )

    def _create_key(self, user, scopes=(BIN_READ,), name="test key"):
        _, api_key = ApiKey.objects.create_key(user=user, name=name, scopes=list(scopes))
        return api_key

    def test_requires_login(self):
        r = self.client.get(reverse("secure:api-key-management"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("login", r.url)

    def test_lists_own_keys(self):
        self._create_key(self.user, name="mine")
        self._create_key(self.admin, name="someone elses")

        self.client.force_login(self.user)
        r = self.client.get(reverse("secure:api-key-management"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "mine")
        self.assertNotContains(r, "someone elses")

    def test_create_key_shows_raw_key_once(self):
        self.client.force_login(self.user)
        r = self.client.post(
            reverse("secure:api-key-create"),
            {"name": "annotate", "scopes": [BIN_READ]},
        )
        self.assertEqual(r.status_code, 302)

        r = self.client.get(reverse("secure:api-key-management"))
        self.assertContains(r, "it will not be shown again")

        api_key = ApiKey.objects.get(user=self.user, name="annotate")
        self.assertEqual(api_key.scopes, [BIN_READ])
        self.assertContains(r, "ifcb_")  # raw key, prefixed
        self.assertNotIn(api_key.hashed_key, str(r.content))  # never the hash

        # the raw key is gone on the next load
        r = self.client.get(reverse("secure:api-key-management"))
        self.assertNotContains(r, "it will not be shown again")

    def test_create_key_requires_a_scope(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("secure:api-key-create"), {"name": "empty"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(ApiKey.objects.filter(user=self.user).count(), 0)

    def test_regular_user_not_offered_sync_scope(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse("secure:api-key-management"))
        self.assertNotContains(r, BIN_SYNC)

    def test_admin_offered_sync_scope(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("secure:api-key-management"))
        self.assertContains(r, BIN_SYNC)

    def test_regular_user_cannot_forgery_grant_sync_scope(self):
        self.client.force_login(self.user)
        r = self.client.post(
            reverse("secure:api-key-create"),
            {"name": "sneaky", "scopes": [BIN_READ, BIN_SYNC]},
        )
        self.assertEqual(r.status_code, 200)  # re-rendered with errors
        self.assertEqual(ApiKey.objects.filter(user=self.user).count(), 0)


    def test_revoke_own_key(self):
        api_key = self._create_key(self.user)
        self.client.force_login(self.user)
        r = self.client.post(reverse("secure:api-key-revoke", args=[api_key.id]))
        self.assertEqual(r.status_code, 302)
        api_key.refresh_from_db()
        self.assertTrue(api_key.revoked)


    def test_cannot_revoke_someone_elses_key(self):
        api_key = self._create_key(self.admin)
        self.client.force_login(self.user)
        r = self.client.post(reverse("secure:api-key-revoke", args=[api_key.id]))
        self.assertEqual(r.status_code, 403)
        api_key.refresh_from_db()
        self.assertFalse(api_key.revoked)

    def test_admin_can_revoke_any_key(self):
        api_key = self._create_key(self.user)
        self.client.force_login(self.admin)
        r = self.client.post(reverse("secure:api-key-revoke", args=[api_key.id]))
        self.assertEqual(r.status_code, 302)
        api_key.refresh_from_db()
        self.assertTrue(api_key.revoked)


    def test_delete_revoked_key(self):
        api_key = self._create_key(self.user)
        api_key.revoked = True
        api_key.save(update_fields=["revoked"])
        self.client.force_login(self.user)
        r = self.client.post(reverse("secure:api-key-delete", args=[api_key.id]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(ApiKey.objects.filter(id=api_key.id).exists())


    def test_delete_expired_key(self):
        "expired keys are dead and may be deleted without revoking first"
        api_key = self._create_key(self.user)
        api_key.expires_at = timezone.now() - timedelta(days=1)
        api_key.save(update_fields=["expires_at"])

        self.client.force_login(self.user)
        r = self.client.post(reverse("secure:api-key-delete", args=[api_key.id]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(ApiKey.objects.filter(id=api_key.id).exists())

    def test_expired_key_row_offers_remove_not_edit(self):
        api_key = self._create_key(self.user, name="dead key")
        api_key.expires_at = timezone.now() - timedelta(days=1)
        api_key.save(update_fields=["expires_at"])

        self.client.force_login(self.user)
        r = self.client.get(reverse("secure:api-key-management"))
        self.assertNotContains(r, reverse("secure:api-key-edit", args=[api_key.id]))
        self.assertContains(r, reverse("secure:api-key-delete", args=[api_key.id]))

    def test_cannot_delete_unrevoked_key(self):
        api_key = self._create_key(self.user)
        self.client.force_login(self.user)
        r = self.client.post(reverse("secure:api-key-delete", args=[api_key.id]))
        self.assertEqual(r.status_code, 302)
        api_key.refresh_from_db()
        self.assertFalse(api_key.revoked)


    def test_cannot_delete_someone_elses_key(self):
        api_key = self._create_key(self.admin)
        api_key.revoked = True
        api_key.save(update_fields=["revoked"])
        self.client.force_login(self.user)
        r = self.client.post(reverse("secure:api-key-delete", args=[api_key.id]))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(ApiKey.objects.filter(id=api_key.id).exists())


    def test_admin_can_delete_any_revoked_key(self):
        api_key = self._create_key(self.user)
        api_key.revoked = True
        api_key.save(update_fields=["revoked"])
        self.client.force_login(self.admin)
        r = self.client.post(reverse("secure:api-key-delete", args=[api_key.id]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(ApiKey.objects.filter(id=api_key.id).exists())


@override_switch("DashboardApi", active=True)
class CreateKeyExpiryAndDescriptionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("expuser", password="pw")
        self.client.force_login(self.user)

    def test_no_expiry_by_default(self):
        self.client.post(
            reverse("secure:api-key-create"),
            {"name": "no expiry", "scopes": [BIN_READ], "expiry": "never"},
        )
        key = ApiKey.objects.get(user=self.user, name="no expiry")
        self.assertIsNone(key.expires_at)

    def test_expiry_in_days(self):
        before = timezone.now()
        self.client.post(
            reverse("secure:api-key-create"),
            {"name": "short lived", "scopes": [BIN_READ], "expiry": "days", "days": "30"},
        )
        key = ApiKey.objects.get(user=self.user, name="short lived")
        expected_low = before + timedelta(days=30) - timedelta(seconds=5)
        expected_high = before + timedelta(days=30) + timedelta(seconds=5)
        self.assertTrue(expected_low <= key.expires_at <= expected_high)

    def test_expiry_days_required_when_expiring(self):
        r = self.client.post(
            reverse("secure:api-key-create"),
            {"name": "broken", "scopes": [BIN_READ], "expiry": "days"},
        )
        self.assertEqual(r.status_code, 200)  # errors re-rendered
        self.assertEqual(ApiKey.objects.filter(user=self.user).count(), 0)

    def test_days_must_be_positive(self):
        r = self.client.post(
            reverse("secure:api-key-create"),
            {"name": "broken", "scopes": [BIN_READ], "expiry": "days", "days": "0"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(ApiKey.objects.filter(user=self.user).count(), 0)

    def test_description_stored(self):
        self.client.post(
            reverse("secure:api-key-create"),
            {
                "name": "annotator",
                "scopes": [BIN_READ],
                "description": "Key for the annotation tool",
                "expiry": "never",
            },
        )
        key = ApiKey.objects.get(user=self.user, name="annotator")
        self.assertEqual(key.description, "Key for the annotation tool")

    def test_description_optional(self):
        self.client.post(
            reverse("secure:api-key-create"),
            {"name": "no desc", "scopes": [BIN_READ], "expiry": "never"},
        )
        key = ApiKey.objects.get(user=self.user, name="no desc")
        self.assertEqual(key.description, "")

    def test_listing_shows_description_and_expiry(self):
        expires = timezone.now() + timedelta(days=7)
        _, key = ApiKey.objects.create_key(
            user=self.user, name="listed", scopes=[BIN_READ],
            description="a note", expires_at=expires,
        )
        r = self.client.get(reverse("secure:api-key-management"))
        self.assertContains(r, "a note")
        self.assertContains(r, key.expires_at.strftime("%Y-%m-%d"))


@override_switch("DashboardApi", active=True)
class EditApiKeyTests(TestCase):
    "Editing a key's scopes/description/expiry; the key value is immutable."

    def setUp(self):
        self.user = User.objects.create_user("edituser", password="pw")
        self.admin = User.objects.create_user("editadmin", password="pw", is_superuser=True)
        self.client.force_login(self.user)

        self.created_at = timezone.now() - timedelta(days=5)
        _, self.api_key = ApiKey.objects.create_key(
            user=self.user, name="editable", scopes=[BIN_READ],
            description="original description",
            expires_at=self.created_at + timedelta(days=30),
        )
        # auto_now_add ignores an explicit created_at on insert; set it directly
        ApiKey.objects.filter(pk=self.api_key.pk).update(created_at=self.created_at)
        self.api_key.refresh_from_db()

    def _edit_url(self):
        return reverse("secure:api-key-edit", args=[self.api_key.id])

    def test_requires_login(self):
        anon = Client(HTTP_HOST="localhost")
        r = anon.get(self._edit_url())
        self.assertEqual(r.status_code, 302)
        self.assertIn("login", r.url)

    def test_cannot_edit_someone_elses_key(self):
        other_user, _ = User.objects.get_or_create(username="other")
        _, other_key = ApiKey.objects.create_key(
            user=other_user, name="theirs", scopes=[BIN_READ]
        )
        r = self.client.get(reverse("secure:api-key-edit", args=[other_key.id]))
        self.assertEqual(r.status_code, 403)

    def test_admin_can_edit_any_key(self):
        self.client.force_login(self.admin)
        r = self.client.get(self._edit_url())
        self.assertEqual(r.status_code, 200)

    def test_form_prefills_scopes_expiry_description(self):
        r = self.client.get(self._edit_url())
        html = r.content.decode()
        self.assertIn("original description", html)
        self.assertIn('name="scopes" value="bins:read" id="id_scopes_0" checked', html)
        self.assertIn('name="expiry" id="expiry-days" value="days" checked', html)
        self.assertIn('name="days" value="30"', html)  # days measured from creation date
        self.assertNotIn("ifcb_", html.split("id_expiry")[0])  # key value not shown

    def test_edit_scopes(self):
        self.client.force_login(self.admin)  # admin may grant bins:sync
        r = self.client.post(self._edit_url(), {
            "description": "original description",
            "scopes": [BIN_READ, BIN_SYNC],
            "expiry": "never",
        })
        self.assertEqual(r.status_code, 302)
        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.scopes, [BIN_READ, BIN_SYNC])
        self.assertIsNone(self.api_key.expires_at)

    def test_edit_expiry_against_creation_date(self):
        "30 days means created_at + 30, not edit time + 30"
        self.client.post(self._edit_url(), {
            "description": "original description",
            "scopes": [BIN_READ],
            "expiry": "days",
            "days": "30",
        })
        self.api_key.refresh_from_db()
        self.assertEqual(
            self.api_key.expires_at, self.created_at + timedelta(days=30)
        )

    def test_cannot_set_expiry_in_the_past(self):
        "a day count smaller than the key's age would expire it immediately"
        r = self.client.post(self._edit_url(), {
            "description": "original description",
            "scopes": [BIN_READ],
            "expiry": "days",
            "days": "4",  # the key is 5 days old
        })
        self.assertEqual(r.status_code, 200)  # re-rendered with errors
        self.assertIn("would put its expiry in the past", r.content.decode())
        self.api_key.refresh_from_db()
        self.assertEqual(
            self.api_key.expires_at, self.created_at + timedelta(days=30)
        )  # unchanged

    def test_edit_never_clears_expiry(self):
        self.client.post(self._edit_url(), {
            "description": "original description",
            "scopes": [BIN_READ],
            "expiry": "never",
        })
        self.api_key.refresh_from_db()
        self.assertIsNone(self.api_key.expires_at)

    def test_edit_description(self):
        self.client.post(self._edit_url(), {
            "description": "updated description",
            "scopes": [BIN_READ],
            "expiry": "never",
        })
        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.description, "updated description")

    def test_key_value_and_prefix_unchanged(self):
        before_hash, before_prefix = self.api_key.hashed_key, self.api_key.prefix
        self.client.post(self._edit_url(), {
            "description": "x",
            "scopes": [BIN_READ],
            "expiry": "never",
        })
        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.hashed_key, before_hash)
        self.assertEqual(self.api_key.prefix, before_prefix)

    def test_cannot_forgery_grant_sync_scope(self):
        r = self.client.post(self._edit_url(), {
            "description": "original description",
            "scopes": [BIN_SYNC],
            "expiry": "never",
        })
        self.assertEqual(r.status_code, 200)  # re-rendered with errors
        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.scopes, [BIN_READ])

    def _expire_key(self):
        self.api_key.expires_at = timezone.now() - timedelta(days=1)
        self.api_key.save(update_fields=["expires_at"])

    def test_revoked_key_redirects_to_management(self):
        self.api_key.revoked = True
        self.api_key.save(update_fields=["revoked"])

        r = self.client.get(self._edit_url())
        self.assertEqual(r.status_code, 302)

    def test_expired_key_redirects_to_management(self):
        "expired keys are dead: like revoked ones, they cannot be edited"
        self._expire_key()

        r = self.client.get(self._edit_url())
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("secure:api-key-management"))

    def test_expired_key_post_does_not_change_key(self):
        "a forged POST against an expired key is ignored"
        self._expire_key()

        r = self.client.post(self._edit_url(), {
            "description": "hacked",
            "scopes": [BIN_SYNC],
            "expiry": "never",
        })
        self.assertEqual(r.status_code, 302)
        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.description, "original description")
        self.assertEqual(self.api_key.scopes, [BIN_READ])

    def test_management_page_shows_edit_button(self):
        r = self.client.get(reverse("secure:api-key-management"))
        self.assertContains(r, reverse("secure:api-key-edit", args=[self.api_key.id]))


@override_switch("DashboardApi", active=True)
class CreateFormVisibilityTests(TestCase):
    "The create form is collapsed until the user clicks Add New Key."

    def setUp(self):
        self.user = User.objects.create_user("formuser", password="pw")
        self.client.force_login(self.user)

    def test_form_hidden_by_default(self):
        r = self.client.get(reverse("secure:api-key-management"))
        self.assertContains(r, 'id="add-key-toggle"')
        self.assertContains(r, 'id="create-key-form" style="display: none;')

    def test_form_visible_when_validation_fails(self):
        r = self.client.post(reverse("secure:api-key-create"), {"name": ""})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'id="create-key-form" style="display: block;')


@override_switch("DashboardApi", active=True)
class UserNavMenuTests(TestCase):
    "The user menu (API Keys / Logout) in the top nav."

    def setUp(self):
        self.user = User.objects.create_user(
            "navuser", password="pw", first_name="Nora", last_name="Vue"
        )
        self.client.force_login(self.user)

    def test_menu_shows_user_name(self):
        r = self.client.get(reverse("secure:api-key-management"))
        self.assertContains(r, "Nora Vue")

    def test_menu_shows_username_when_no_name(self):
        User.objects.filter(username="navuser").update(first_name="", last_name="")
        r = self.client.get(reverse("secure:api-key-management"))
        self.assertContains(r, "navuser")

    def test_menu_items(self):
        r = self.client.get(reverse("secure:api-key-management"))
        self.assertContains(r, "API Keys")
        self.assertContains(r, reverse("secure:logout"))

class ApiKeyGatingTests(TestCase):
    "API key management is gated behind the DashboardApi waffle switch."

    def setUp(self):
        self.user = User.objects.create_user("gateduser", password="pw")
        self.admin = User.objects.create_user(
            "gateadmin", password="pw", is_superuser=True
        )
        self.client.force_login(self.user)

    def _create_key(self, revoked=False):
        _, api_key = ApiKey.objects.create_key(
            user=self.user, name="gated key", scopes=[BIN_READ]
        )
        if revoked:
            api_key.revoked = True
            api_key.save(update_fields=["revoked"])
        return api_key

    @override_switch("DashboardApi", active=False)
    def test_management_page_404_when_switch_off(self):
        r = self.client.get(reverse("secure:api-key-management"))
        self.assertEqual(r.status_code, 404)

    @override_switch("DashboardApi", active=False)
    def test_create_404_when_switch_off(self):
        r = self.client.post(
            reverse("secure:api-key-create"),
            {"name": "k", "scopes": [BIN_READ]},
        )
        self.assertEqual(r.status_code, 404)
        self.assertEqual(ApiKey.objects.filter(user=self.user).count(), 0)

    @override_switch("DashboardApi", active=False)
    def test_edit_404_when_switch_off(self):
        api_key = self._create_key()
        r = self.client.get(reverse("secure:api-key-edit", args=[api_key.id]))
        self.assertEqual(r.status_code, 404)

    @override_switch("DashboardApi", active=False)
    def test_revoke_404_when_switch_off(self):
        api_key = self._create_key()
        r = self.client.post(reverse("secure:api-key-revoke", args=[api_key.id]))
        self.assertEqual(r.status_code, 404)
        api_key.refresh_from_db()
        self.assertFalse(api_key.revoked)

    @override_switch("DashboardApi", active=False)
    def test_delete_404_when_switch_off(self):
        api_key = self._create_key(revoked=True)
        r = self.client.post(reverse("secure:api-key-delete", args=[api_key.id]))
        self.assertEqual(r.status_code, 404)
        self.assertTrue(ApiKey.objects.filter(id=api_key.id).exists())

    @override_switch("DashboardApi", active=True)
    def test_management_page_renders_when_switch_on(self):
        r = self.client.get(reverse("secure:api-key-management"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "API Keys")

    @override_switch("DashboardApi", active=False)
    def test_nav_menu_hides_api_keys_but_keeps_logout_when_switch_off(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("secure:index"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "/secure/api-keys")
        self.assertContains(r, "Logout")

    @override_switch("DashboardApi", active=True)
    def test_nav_menu_shows_api_keys_when_switch_on(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("secure:index"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "/secure/api-keys")
