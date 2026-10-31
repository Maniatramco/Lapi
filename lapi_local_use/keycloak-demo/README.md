# Keycloak + OpenFGA on your own PC

A local Keycloak, OpenFGA and Lapi (api + web) to try Keycloak sign-in end to end.
Everything listens on 127.0.0.1 only. The accounts and the client secret are test values for this demo:
never reuse them anywhere else.

## Start

```powershell
.\start.ps1
```

The first start creates `.env` with a random Lapi master key and takes a minute while Keycloak imports the realm.
Then create the break-glass administrator (Lapi's own password sign-in), once:

```powershell
'{"username":"breakglass","password":"breakglass-demo-pass"}' | docker exec -i lapi-keycloak-demo-api-1 python -m lapi_app.create_admin
```

| What | Where | Sign in |
| --- | --- | --- |
| Lapi | http://localhost:3100 | **Sign in with Keycloak** |
| Keycloak admin console | http://localhost:8180/admin | `admin` / `admin` |
| Test administrator (has realm role `lapi-administrator`) | Keycloak realm `lapi` | `alice` / `alice-demo-pass` |
| Test user (no role, in group `Finance`) | Keycloak realm `lapi` | `bob` / `bob-demo-pass` |
| Test auditor (has realm role `lapi-auditor`) | Keycloak realm `lapi` | `carol` / `carol-demo-pass` |
| Break-glass administrator | Lapi, "Administrator sign-in without Keycloak" | `breakglass` / `breakglass-demo-pass` |

The `lapi` client sends Keycloak groups in a `groups` claim (Group Membership mapper, full path): each
group becomes a Lapi team at sign-in. The realm locks an account for a while after 5 failed passwords.

## What to check

1. **alice** signs in through Keycloak and lands as an **Administrator**. Users & passwords lists her with "Keycloak".
2. **Sign out** ends the session at Keycloak too (Keycloak asks "Do you want to log out?").
3. **bob** signs in as a normal **User**: no datasets, and no admin pages. Lapi now has the team **Finance** with bob in it.
4. As alice, create a dataset and open **Access map**: give bob **Viewer** (click his cell once), or give the
   **Finance** team **Editor**, and save. bob sees the dataset after a refresh; as Viewer he can chat and read but
   not upload, as Editor he can upload and extract. That check is answered by OpenFGA.
5. Give bob **Owner**: his Manage dataset screen gets a **Members** tab where he can share the dataset himself.
6. **carol** signs in as an **Auditor**: she sees Users & passwords and Access map read-only, and no dataset content.
7. In the Keycloak console (realm `lapi` → Users → bob → Role mapping), give bob `lapi-administrator`.
   He becomes an administrator at his next sign-in. Remove it, and he becomes a user again.
8. In Keycloak, disable bob. His next sign-in fails; a running Lapi session lasts until it expires (12 hours)
   or is removed by deleting his Lapi account.

## Stop

```powershell
docker compose -p lapi-keycloak-demo down       # keep data
docker compose -p lapi-keycloak-demo down -v    # also delete the demo's Lapi data
```

Port 3100 is used because 3000 is often taken. To use other Lapi images, set `LAPI_API_IMAGE` and `LAPI_WEB_IMAGE` in `.env`.
