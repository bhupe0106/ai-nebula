from django.contrib.auth import get_user_model
from django.test import TestCase

from .services import quota_for, quota_status, record_usage, tokens_used

User = get_user_model()


class QuotaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="quota@example.com", password="password12345")

    def test_new_user_has_full_quota(self):
        status = quota_status(self.user)
        self.assertEqual(status["used"], 0)
        self.assertFalse(status["exceeded"])
        self.assertEqual(status["remaining"], self.user.profile.monthly_token_quota)

    def test_usage_counts_prompt_and_completion(self):
        record_usage(user=self.user, prompt_tokens=10, completion_tokens=15)
        record_usage(user=self.user, prompt_tokens=5, completion_tokens=5)
        self.assertEqual(tokens_used(self.user), 35)
        self.assertEqual(quota_status(self.user)["used"], 35)

    def test_exceeded_when_usage_reaches_quota(self):
        self.user.profile.monthly_token_quota = 20
        self.user.profile.save(update_fields=["monthly_token_quota"])
        record_usage(user=self.user, prompt_tokens=20, completion_tokens=0)
        self.assertTrue(quota_status(self.user)["exceeded"])

    def test_zero_quota_means_unlimited(self):
        self.user.profile.monthly_token_quota = 0
        self.user.profile.save(update_fields=["monthly_token_quota"])
        status = quota_status(self.user)
        self.assertTrue(status["unlimited"])
        self.assertIsNone(status["remaining"])

    def test_profile_fallback(self):
        self.assertEqual(quota_for(self.user), self.user.profile.monthly_token_quota)
