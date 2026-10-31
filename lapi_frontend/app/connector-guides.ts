/** Plain-language, step-by-step setup guides shown on Add knowledge for each storage connector.
 * Text in `backticks` is shown as code: something to copy, type or look for exactly. */
export type GuidePart={title:string;steps:string[]};
export type ConnectorGuide={time:string;need:string[];parts:GuidePart[];fields:[string,string][];problems:[string,string][]};

const AFTER:GuidePart={title:'Finish in Lapi',steps:[
 'Fill in the form below with the values you copied (see "What goes where"), then click `Test connection`. You should see "Read access verified" with the number of files and folders found.',
 'Click `Save and browse documents`.',
 'Open folders and tick the files you want, up to 20 at a time. Files marked "Unsupported file type" cannot be imported; PDF, DOCX, TXT, JSON, spreadsheets (XLSX, CSV, TSV) and images (PNG, JPG, WEBP) can.',
 'Tick `Everyone who can access … may read these copies`, then click `Vectorize`.',
 'Wait until each file shows `Ready to ask`, then click `Ask about these documents`. You can leave the page meanwhile; it keeps going.',
 'Images and scanned pages are read with OCR. Their collection needs an OCR model: register `gpt-4o-mini` (OpenAI) or a Gemini model for Extraction and select it as the collection\'s OCR model in Collection Model Mapping.',
]};

export const CONNECTOR_GUIDES:Record<string,ConnectorGuide>={
 google_drive:{time:'About 10 minutes, once',
  need:['A Google account that can open the Drive folder','The folder you want Lapi to read'],
  parts:[
   {title:'Create a Google Cloud project (one time)',steps:[
    'Go to `console.cloud.google.com` and sign in with your Google account.',
    'Click the project picker at the top of the page, then `New project`.',
    'Project name: `lapi`. Organization and Location: leave `No organization` for a personal account (for a work account, pick your company). Click `Create`, then select the new project at the top.',
    'In the search bar at the top, type `Google Drive API`, open it and click `Enable`.']},
   {title:'Create a "robot" account and its key',steps:[
    'Open the menu ☰ → `IAM & Admin` → `Service Accounts` → `Create service account`.',
    'Name: `lapi-drive-reader`. Click `Create and continue`, skip the roles step, click `Done`.',
    'Click the new service account, open the `Keys` tab → `Add key` → `Create new key` → `JSON` → `Create`. A .json file downloads to your computer. Keep it private.',
    'Copy the service account email. It looks like `lapi-drive-reader@lapi-123456.iam.gserviceaccount.com`.']},
   {title:'Share the folder with the robot account',steps:[
    'Open `drive.google.com`, right-click your folder → `Share`.',
    'Paste the service account email, set it to `Viewer`, untick `Notify people`, click `Share`.',
    'Open the folder. In the address bar, copy the part after `/folders/` (stop before any `?`). That is the folder ID.']},
   AFTER],
  fields:[
   ['Google Drive folder ID','The part of the folder address after /folders/, for example 1AbCdEfGhIjKlMnOp.'],
   ['Service-account JSON key','Open the downloaded .json file in Notepad, select all (Ctrl+A), copy and paste everything.']],
  problems:[
   ['Google Drive folder not found for …@….iam.gserviceaccount.com','The folder is not shared with that email as Viewer, or the folder ID has extra characters (remove ?usp=… and spaces).'],
   ['Google rejected the service-account key','Turn on Google Drive API in the same project as the key, or create a new key; deleted keys stop working.'],
   ['Enter a Google service-account JSON key','Paste the whole .json file, from the first { to the last }.']]},

 gcs:{time:'About 10 minutes, once',
  need:['Access to the Google Cloud project that owns the bucket','The bucket name'],
  parts:[
   {title:'Create a "robot" account and its key',steps:[
    'Go to `console.cloud.google.com` and select the project that owns the bucket (project picker at the top).',
    'Open the menu ☰ → `IAM & Admin` → `Service Accounts` → `Create service account`.',
    'Name: `lapi-storage-reader`. Click `Create and continue`, skip the roles step, click `Done`.',
    'Click the new service account → `Keys` tab → `Add key` → `Create new key` → `JSON` → `Create`. A .json file downloads. Keep it private.',
    'Copy the service account email (it ends in `.iam.gserviceaccount.com`).']},
   {title:'Let it read your bucket',steps:[
    'Open the menu ☰ → `Cloud Storage` → `Buckets` and click your bucket. Its name is shown at the top; copy it.',
    'Open the `Permissions` tab → `Grant access`.',
    'New principals: paste the service account email. Role: `Storage Object Viewer`. Click `Save`.',
    'Optional: to limit Lapi to one folder, open the folder and note its path, for example `invoices/2026/`.']},
   AFTER],
  fields:[
   ['Cloud Storage bucket','The bucket name only, for example my-company-docs (no gs://).'],
   ['Folder prefix','Optional. A folder path ending in /, for example invoices/. Leave empty for the whole bucket.'],
   ['Service-account JSON key','Open the downloaded .json file in Notepad, select all, copy and paste everything.']],
  problems:[
   ['Access was denied. Grant … Storage Object Viewer','Repeat "Let it read your bucket" with exactly the email shown in the message.'],
   ['Bucket not found','Check the bucket name for typos; remove gs:// and any folder part.'],
   ['Google rejected the service-account key','Create a new key in the same project; deleted keys stop working.']]},

 s3:{time:'About 10 minutes, once',
  need:['An AWS account that can manage IAM users','The S3 bucket name and its region'],
  parts:[
   {title:'Find the bucket name and region',steps:[
    'Sign in at `console.aws.amazon.com` and open `S3`.',
    'Find your bucket in the list. Copy its name, and note the `AWS Region` column, for example `Asia Pacific (Mumbai) ap-south-1`; you need the code `ap-south-1`.']},
   {title:'Create a read-only user for Lapi',steps:[
    'Open `IAM` → `Users` → `Create user`. User name: `lapi-reader`. Do not tick console access. Click `Next`.',
    'Choose `Attach policies directly` → `Create policy` (opens a new tab) → `JSON`.',
    'Paste this, replacing YOUR-BUCKET with your bucket name: `{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"s3:ListBucket","Resource":"arn:aws:s3:::YOUR-BUCKET"},{"Effect":"Allow","Action":"s3:GetObject","Resource":"arn:aws:s3:::YOUR-BUCKET/*"}]}`',
    'Click `Next`, name it `lapi-read-YOUR-BUCKET`, click `Create policy`. Back in the first tab, refresh the list, tick the new policy, click `Next` → `Create user`.']},
   {title:'Create the access key',steps:[
    'Open the new user → `Security credentials` tab → `Create access key`.',
    'Choose `Application running outside AWS` → `Next` → `Create access key`.',
    'Copy the `Access key ID` and the `Secret access key`. The secret is shown only once; you can also click `Download .csv file`.']},
   AFTER],
  fields:[
   ['S3 bucket','The bucket name only (no s3://).'],
   ['AWS region','The region code, for example ap-south-1.'],
   ['Folder prefix','Optional. A folder path ending in /, for example contracts/.'],
   ['Expected bucket owner','Optional. Your 12-digit AWS account ID, shown under your name at the top right.'],
   ['Sign-in method','Keep Access key.'],
   ['Access key ID / Secret access key','From "Create the access key". Leave Session token empty.']],
  problems:[
   ['The access key ID was not recognised','Copy the Access key ID again with no spaces; it must belong to the same AWS account as the bucket.'],
   ['The secret does not match the access key ID','Paste the secret again. If it is lost, create a new access key.'],
   ['The bucket is in a different region','Use the region code shown for the bucket in the S3 list.'],
   ['Access was denied','The policy must name your exact bucket: ListBucket on the bucket and GetObject on bucket/*.']]},

 azure_blob:{time:'About 5 minutes; repeat when the token expires',
  need:['Access to the Azure storage account in portal.azure.com','The container that holds your documents'],
  parts:[
   {title:'Find the account and container names',steps:[
    'Sign in at `portal.azure.com` and open `Storage accounts`. Click your account; its name (for example `contosodocs`) is the storage account name.',
    'In the left menu open `Data storage` → `Containers` and note the container name.']},
   {title:'Create a read-only access token (SAS)',steps:[
    'Click the container → in its left menu open `Shared access tokens`.',
    'Signing method: `Account key`. Permissions: tick only `Read` and `List`.',
    'Set an Expiry date (for example one year from today). Allowed protocols: `HTTPS only`.',
    'Click `Generate SAS token and URL` and copy the `Blob SAS token`. Lapi stops reading when it expires; create a new one then.']},
   {title:'If your storage account has a firewall',steps:[
    'Open `Security + networking` → `Networking`. If public access is `Enabled from selected networks`, ask your administrator to add the Lapi server\'s outgoing IP address.']},
   AFTER],
  fields:[
   ['Storage account','The account name, for example contosodocs (lowercase letters and digits).'],
   ['Container','The container name.'],
   ['Folder prefix','Optional. A folder path ending in /.'],
   ['Container SAS token','The Blob SAS token, starting with sp= or sv=. Pasting the whole SAS URL also works.']],
  problems:[
   ['The SAS token was rejected','It expired or was copied from another account. Generate a new one.'],
   ['The SAS token cannot list or read this container','Generate it again with both Read and List ticked.'],
   ['Use a read-only SAS token','Untick every permission except Read and List.'],
   ['Azure refused access / limited to other IP addresses','The storage firewall or IP limit blocks Lapi; see "If your storage account has a firewall".']]},

 oci_object:{time:'About 10 minutes, once',
  need:['An Oracle Cloud user that can read the bucket','The bucket\'s namespace, name and region'],
  parts:[
   {title:'Find the bucket details',steps:[
    'Sign in at `cloud.oracle.com`. Open the menu ☰ → `Storage` → `Buckets` and choose the compartment that holds your bucket.',
    'Click the bucket. On `Bucket information`, copy the `Namespace` and the bucket name.',
    'Note the region shown at the top right, for example `India West (Mumbai)`; its code is `ap-mumbai-1` (Hyderabad is `ap-hyderabad-1`).']},
   {title:'Create a customer secret key',steps:[
    'Click your profile picture at the top right → `My profile`.',
    'Under `Resources` (or the `Tokens and keys` tab) choose `Customer secret keys` → `Generate secret key`. Name: `lapi`.',
    'Copy the secret now; it is shown only once. Close the window, then copy the `Access key` shown in the list.']},
   {title:'Make sure the user may read the bucket',steps:[
    'Your administrator needs a policy for your group, for example: `Allow group Lapi-Readers to read buckets in compartment Documents` and `Allow group Lapi-Readers to read objects in compartment Documents`.']},
   AFTER],
  fields:[
   ['Object Storage namespace','From Bucket information, for example bmyljaecivrj.'],
   ['Bucket','The bucket name.'],
   ['Region','The region code, for example ap-mumbai-1.'],
   ['Folder prefix','Optional. A folder path ending in /.'],
   ['Customer secret key: access key / secret','From "Create a customer secret key".']],
  problems:[
   ['The customer secret key ID was not recognised','Copy the Access key from the list again; it must be from this tenancy.'],
   ['The secret does not match','Paste the secret again. If it is lost, generate a new customer secret key.'],
   ['Could not reach the storage endpoint','Check the namespace and region code.'],
   ['Access was denied','Ask your administrator to add the read policies above for your group.']]},

 sharepoint:{time:'About 20 minutes, once; needs a Microsoft 365 administrator',
  need:['A Microsoft 365 administrator (to approve the app)','The SharePoint site that holds your documents'],
  parts:[
   {title:'Register an app for Lapi',steps:[
    'Sign in at `entra.microsoft.com` → `Applications` → `App registrations` → `New registration`.',
    'Name: `Lapi reader`. Supported account types: `Accounts in this organizational directory only`. Click `Register`.',
    'On the Overview page copy the `Application (client) ID` and the `Directory (tenant) ID`.']},
   {title:'Create a client secret',steps:[
    'Open `Certificates & secrets` → `New client secret`. Description: `lapi`, choose an expiry, click `Add`.',
    'Copy the `Value` column right away (not the Secret ID). It is hidden once you leave the page.']},
   {title:'Allow the app to read SharePoint',steps:[
    'Open `API permissions` → `Add a permission` → `Microsoft Graph` → `Application permissions`.',
    'Search `Sites.Read.All`, tick it, click `Add permissions`.',
    'Click `Grant admin consent for <your organisation>` (an administrator must do this). The status should turn green.']},
   {title:'Find the site and library IDs',steps:[
    'Open `developer.microsoft.com/graph/graph-explorer` and sign in with your work account.',
    'Run a GET for `https://graph.microsoft.com/v1.0/sites/YOURCOMPANY.sharepoint.com:/sites/SITENAME` (use the address of your site). Copy the `id` value; it looks like `yourcompany.sharepoint.com,1234…,5678…`. That is the site ID.',
    'Run a GET for `https://graph.microsoft.com/v1.0/sites/SITE-ID/drives`. Find the library, usually `Documents`, and copy its `id` (starts with `b!`). That is the drive ID.',
    'Optional, to limit Lapi to one folder: run `https://graph.microsoft.com/v1.0/drives/DRIVE-ID/root/children` and copy the folder\'s `id`.']},
   AFTER],
  fields:[
   ['Entra tenant ID','Directory (tenant) ID from the app Overview page.'],
   ['Application client ID','Application (client) ID from the same page.'],
   ['Application client secret','The secret Value (not its ID).'],
   ['SharePoint site ID','The id from Graph Explorer (hostname,number,number), not the site URL.'],
   ['Document library drive ID','The library id starting with b!.'],
   ['Folder item ID','Optional; leave empty for the whole library.']],
  problems:[
   ['Microsoft sign-in failed','Check the tenant ID, client ID and secret Value, and that the secret has not expired.'],
   ['The Entra application cannot read this site','Add Sites.Read.All (Application) and click Grant admin consent.'],
   ['SharePoint site not found','Use the site id from Graph Explorer, not the web address.'],
   ['The document library does not belong to the configured site','Get the drive ID again from that same site\'s /drives list.']]},
};
