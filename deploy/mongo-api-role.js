// Run manually in an authenticated mongosh administrative session.
// Set MONGODB_DATABASE in that shell to the SAME database as your root .env.
// This script neither creates a user nor prints/stores passwords.
const name = process.env.MONGODB_DATABASE;
if (!name) throw new Error('Set MONGODB_DATABASE to your existing application database.');
const app = db.getSiblingDB(name);
const role = 'superdealPublicApi';
const privileges = [
  ...['fact_table','pipeline_status','pipeline_logs','ek_raw','playwright_raw'].map(collection => ({resource:{db:name,collection},actions:['find']})),
  ...['deal_clicks','deal_alerts','alert_confirmations','alert_deliveries'].map(collection => ({resource:{db:name,collection},actions:['find','insert','update','remove','createIndex']})),
];
if (app.getRole(role)) app.updateRole(role,{privileges,roles:[]});
else app.createRole({role,privileges,roles:[]});
print('Role prepared. Create a dedicated API user interactively with passwordPrompt(), and assign this role.');
