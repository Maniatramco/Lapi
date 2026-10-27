"""Create the OCI Vault, HSM key, dynamic group and policy that let lapi-vm read its master key.

Run on a computer whose OCI config (~/.oci/config) may manage vaults, keys and IAM:
  python ags_deploy/scripts/setup-lapi-vault.py
Safe to re-run: existing resources with these names are reused. Prints the IDs to use next.
"""
import json
import oci

COMPARTMENT, INSTANCE = 'lapi', 'lapi-vm'
VAULT, KEY, GROUP, POLICY = 'lapi-vault', 'lapi-master-encryption-key', 'lapi-vm', 'lapi-vault-access'

cfg = oci.config.from_file()
tenancy = cfg['tenancy']
identity = oci.identity.IdentityClient(cfg)
compartment = next(c for c in identity.list_compartments(tenancy, lifecycle_state='ACTIVE').data if c.name == COMPARTMENT).id
compute = oci.core.ComputeClient(cfg)
instance = next(i for i in compute.list_instances(compartment).data
                if i.display_name == INSTANCE and i.lifecycle_state != 'TERMINATED').id

kms = oci.key_management.KmsVaultClient(cfg)
models = oci.key_management.models
vault = next((v for v in kms.list_vaults(compartment).data
              if v.display_name == VAULT and v.lifecycle_state in ('ACTIVE', 'CREATING')), None)
if not vault:
    vault = kms.create_vault(models.CreateVaultDetails(compartment_id=compartment, display_name=VAULT, vault_type='DEFAULT')).data
    print('Vault: creating (a few minutes)')
vault = oci.wait_until(kms, kms.get_vault(vault.id), 'lifecycle_state', 'ACTIVE', max_wait_seconds=1200).data
print('Vault: active')

keys = oci.key_management.KmsManagementClient(cfg, service_endpoint=vault.management_endpoint)
key = next((k for k in keys.list_keys(compartment).data
            if k.display_name == KEY and k.lifecycle_state in ('ENABLED', 'CREATING')), None)
if not key:
    key = keys.create_key(models.CreateKeyDetails(compartment_id=compartment, display_name=KEY, protection_mode='HSM',
                                                  key_shape=models.KeyShape(algorithm='AES', length=32))).data
    print('Key: creating')
key = oci.wait_until(keys, keys.get_key(key.id), 'lifecycle_state', 'ENABLED', max_wait_seconds=600).data
print('Key: enabled')

if not any(g.name == GROUP for g in identity.list_dynamic_groups(tenancy).data):
    identity.create_dynamic_group(oci.identity.models.CreateDynamicGroupDetails(
        compartment_id=tenancy, name=GROUP, description='The lapi-vm instance',
        matching_rule=f"ALL {{instance.id = '{instance}'}}"))
    print('Dynamic group: created')

# Reading is permanent. Managing secrets and using the key are only needed for the
# one-time "store" step; remove those two statements afterwards if you prefer.
statements = [
    f"Allow dynamic-group {GROUP} to read secret-bundles in compartment {COMPARTMENT} where target.vault.id = '{vault.id}'",
    f"Allow dynamic-group {GROUP} to manage secrets in compartment {COMPARTMENT} where target.vault.id = '{vault.id}'",
    f"Allow dynamic-group {GROUP} to use keys in compartment {COMPARTMENT} where target.key.id = '{key.id}'",
]
if not any(p.name == POLICY for p in identity.list_policies(compartment).data):
    identity.create_policy(oci.identity.models.CreatePolicyDetails(
        compartment_id=compartment, name=POLICY, description='lapi-vm reads its master key from lapi-vault',
        statements=statements))
    print('Policy: created')

print(json.dumps({'compartment_id': compartment, 'vault_id': vault.id, 'key_id': key.id, 'region': cfg['region']}, indent=2))
