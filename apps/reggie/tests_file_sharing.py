from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from apps.users.models import CustomUser
from apps.teams.models import Team
from apps.reggie.models import Project, VaultFile

# For creating dummy files for VaultFile
from django.core.files.uploadedfile import SimpleUploadedFile

class VaultFileSharingTests(APITestCase):
    def setUp(self):
        # Users
        self.project_owner_user = CustomUser.objects.create_user(username='vf_project_owner', email='vf_po@test.com', password='password123', display_name='VF Project Owner')
        self.project_member_user = CustomUser.objects.create_user(username='vf_project_member', email='vf_pm@test.com', password='password123', display_name='VF Project Member')
        self.team_member_user = CustomUser.objects.create_user(username='vf_team_member', email='vf_tm@test.com', password='password123', display_name='VF Team Member')
        self.main_team_user = CustomUser.objects.create_user(username='vf_main_team_member', email='vf_mtm@test.com', password='password123', display_name='VF Main Team Member')
        self.direct_vault_share_user = CustomUser.objects.create_user(username='vf_direct_share', email='vf_ds@test.com', password='password123', display_name='VF Direct Share User')
        self.other_user = CustomUser.objects.create_user(username='vf_other', email='vf_other@test.com', password='password123', display_name='VF Other User')
        self.superuser = CustomUser.objects.create_superuser(username='vf_superuser', email='vf_su@test.com', password='password123')

        # Teams
        self.project_team = Team.objects.create(name='VF Project Team', owner=self.project_owner_user) # Main team for project_a
        self.project_sharing_team = Team.objects.create(name='VF Project Sharing Team', owner=self.project_owner_user)
        self.direct_share_team = Team.objects.create(name='VF Direct Share Team', owner=self.project_owner_user)

        # Add users to teams
        self.project_team.members.add(self.main_team_user)
        self.project_sharing_team.members.add(self.team_member_user)
        self.direct_share_team.members.add(self.team_member_user) # team_member_user is also in this team for a direct share test

        # Project
        self.project_a = Project.objects.create(
            name='Project A for VaultFiles',
            owner=self.project_owner_user,
            team=self.project_team # Assign main team
        )

        # Dummy file content
        self.dummy_file_content = b"This is a dummy file for vault testing."
        self.dummy_file = SimpleUploadedFile("vault_test_file.txt", self.dummy_file_content, content_type="text/plain")
        self.dummy_file_direct = SimpleUploadedFile("direct_share_vault_file.txt", self.dummy_file_content, content_type="text/plain")


        # VaultFiles
        self.vf_in_project_a = VaultFile.objects.create(
            original_filename='file_in_project_a.txt',
            uploaded_by=self.project_owner_user,
            project=self.project_a,
            file=self.dummy_file
        )
        self.vf_direct_share = VaultFile.objects.create(
            original_filename='file_for_direct_share.txt',
            uploaded_by=self.project_owner_user,
            file=self.dummy_file_direct
            # No project linked initially
        )

        self.client = APIClient()
        self.vaultfile_list_url = reverse('vaultfile-list') # Adjust if your router name is different
        # self.vaultfile_detail_url_project_a = reverse('vaultfile-detail', kwargs={'pk': self.vf_in_project_a.pk})
        # self.vaultfile_detail_url_direct_share = reverse('vaultfile-detail', kwargs={'pk': self.vf_direct_share.pk})

    def get_detail_url(self, pk):
        return reverse('vaultfile-detail', kwargs={'pk': pk})

    # --- 1. Direct Ownership Tests ---
    def test_owner_can_list_and_retrieve_owned_vault_files(self):
        self.client.force_authenticate(user=self.project_owner_user)

        # List
        response_list = self.client.get(self.vaultfile_list_url)
        self.assertEqual(response_list.status_code, status.HTTP_200_OK)
        response_pks = [item['id'] for item in response_list.data.get('results', response_list.data)]
        self.assertIn(self.vf_in_project_a.pk, response_pks)
        self.assertIn(self.vf_direct_share.pk, response_pks)

        # Retrieve vf_in_project_a
        response_detail_project = self.client.get(self.get_detail_url(self.vf_in_project_a.pk))
        self.assertEqual(response_detail_project.status_code, status.HTTP_200_OK)
        self.assertEqual(response_detail_project.data['id'], self.vf_in_project_a.pk)

        # Retrieve vf_direct_share
        response_detail_direct = self.client.get(self.get_detail_url(self.vf_direct_share.pk))
        self.assertEqual(response_detail_direct.status_code, status.HTTP_200_OK)
        self.assertEqual(response_detail_direct.data['id'], self.vf_direct_share.pk)

    # --- 2. Direct Sharing of VaultFile Tests ---
    def test_user_directly_shared_with_can_access_vault_file(self):
        self.vf_direct_share.shared_with_users.add(self.direct_vault_share_user)
        self.client.force_authenticate(user=self.direct_vault_share_user)

        response_list = self.client.get(self.vaultfile_list_url)
        self.assertEqual(response_list.status_code, status.HTTP_200_OK)
        self.assertIn(self.vf_direct_share.pk, [item['id'] for item in response_list.data.get('results', response_list.data)])
        self.assertNotIn(self.vf_in_project_a.pk, [item['id'] for item in response_list.data.get('results', response_list.data)])


        response_detail = self.client.get(self.get_detail_url(self.vf_direct_share.pk))
        self.assertEqual(response_detail.status_code, status.HTTP_200_OK)

    def test_team_member_can_access_vault_file_shared_with_team(self):
        self.vf_direct_share.shared_with_teams.add(self.direct_share_team) # team_member_user is in direct_share_team
        self.client.force_authenticate(user=self.team_member_user)

        response_list = self.client.get(self.vaultfile_list_url)
        self.assertEqual(response_list.status_code, status.HTTP_200_OK)
        self.assertIn(self.vf_direct_share.pk, [item['id'] for item in response_list.data.get('results', response_list.data)])

        response_detail = self.client.get(self.get_detail_url(self.vf_direct_share.pk))
        self.assertEqual(response_detail.status_code, status.HTTP_200_OK)

    # --- 3. Project-Based Access for vf_in_project_a ---
    def test_project_member_can_access_vault_file_in_project(self):
        self.project_a.members.add(self.project_member_user)
        self.client.force_authenticate(user=self.project_member_user)

        response_list = self.client.get(self.vaultfile_list_url)
        self.assertEqual(response_list.status_code, status.HTTP_200_OK)
        self.assertIn(self.vf_in_project_a.pk, [item['id'] for item in response_list.data.get('results', response_list.data)])

        response_detail = self.client.get(self.get_detail_url(self.vf_in_project_a.pk))
        self.assertEqual(response_detail.status_code, status.HTTP_200_OK)

    def test_project_main_team_member_can_access_vault_file_in_project(self):
        # self.main_team_user is in self.project_team, which is project_a.team
        self.client.force_authenticate(user=self.main_team_user)

        response_list = self.client.get(self.vaultfile_list_url)
        self.assertEqual(response_list.status_code, status.HTTP_200_OK)
        self.assertIn(self.vf_in_project_a.pk, [item['id'] for item in response_list.data.get('results', response_list.data)])

        response_detail = self.client.get(self.get_detail_url(self.vf_in_project_a.pk))
        self.assertEqual(response_detail.status_code, status.HTTP_200_OK)

    def test_member_of_team_project_is_shared_with_can_access_vault_file(self):
        self.project_a.shared_with_teams.add(self.project_sharing_team) # team_member_user is in project_sharing_team
        self.client.force_authenticate(user=self.team_member_user)

        response_list = self.client.get(self.vaultfile_list_url)
        self.assertEqual(response_list.status_code, status.HTTP_200_OK)
        self.assertIn(self.vf_in_project_a.pk, [item['id'] for item in response_list.data.get('results', response_list.data)])

        # Also check they can access vf_direct_share if it was shared with direct_share_team (which team_member_user is also part of)
        self.vf_direct_share.shared_with_teams.add(self.direct_share_team)
        response_list_updated = self.client.get(self.vaultfile_list_url)
        self.assertIn(self.vf_direct_share.pk, [item['id'] for item in response_list_updated.data.get('results', response_list_updated.data)])


        response_detail = self.client.get(self.get_detail_url(self.vf_in_project_a.pk))
        self.assertEqual(response_detail.status_code, status.HTTP_200_OK)

    # --- 4. No Access Tests ---
    def test_other_user_cannot_access_unrelated_vault_files(self):
        self.client.force_authenticate(user=self.other_user)

        # List
        response_list = self.client.get(self.vaultfile_list_url)
        self.assertEqual(response_list.status_code, status.HTTP_200_OK)
        # Expect empty list or list without these specific files
        response_pks = [item['id'] for item in response_list.data.get('results', response_list.data)]
        self.assertNotIn(self.vf_in_project_a.pk, response_pks)
        self.assertNotIn(self.vf_direct_share.pk, response_pks)


        # Retrieve vf_in_project_a
        response_detail_project = self.client.get(self.get_detail_url(self.vf_in_project_a.pk))
        self.assertEqual(response_detail_project.status_code, status.HTTP_404_NOT_FOUND)

        # Retrieve vf_direct_share
        response_detail_direct = self.client.get(self.get_detail_url(self.vf_direct_share.pk))
        self.assertEqual(response_detail_direct.status_code, status.HTTP_404_NOT_FOUND)

    # --- 5. Superuser Access ---
    def test_superuser_can_list_and_retrieve_all_vault_files(self):
        self.client.force_authenticate(user=self.superuser)

        # List
        response_list = self.client.get(self.vaultfile_list_url)
        self.assertEqual(response_list.status_code, status.HTTP_200_OK)
        response_pks = [item['id'] for item in response_list.data.get('results', response_list.data)]
        self.assertIn(self.vf_in_project_a.pk, response_pks)
        self.assertIn(self.vf_direct_share.pk, response_pks)

        # Retrieve vf_in_project_a
        response_detail_project = self.client.get(self.get_detail_url(self.vf_in_project_a.pk))
        self.assertEqual(response_detail_project.status_code, status.HTTP_200_OK)

        # Retrieve vf_direct_share
        response_detail_direct = self.client.get(self.get_detail_url(self.vf_direct_share.pk))
        self.assertEqual(response_detail_direct.status_code, status.HTTP_200_OK)

    # --- Comment on FileViewSet ---
    # If the main FileViewSet (for apps.reggie.models.File) also uses Q(vault_project__owner=user),
    # Q(vault_project__members=user), etc., in its get_queryset for files that have is_vault_file=True
    # or are linked to a vault_project, then similar tests should be written for that ViewSet.
    # The current VaultFileViewSet.get_queryset is quite specific with its OR conditions,
    # covering direct ownership/sharing of the VaultFile itself OR cascaded permissions from the Project.
    # This test suite focuses on validating that VaultFileViewSet.get_queryset.
```
