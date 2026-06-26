// Sets a GitHub Projects (v2) Number field on one or more issue/PR items to
// that run's Claude action cost. Run via actions/github-script's
// `script-path`, with a token that has Projects access (CAIRN_BOT_TOKEN --
// the default GITHUB_TOKEN cannot write to a user/org-level Project).
//
// Env vars:
//   PROJECT_OWNER       login of the user/org that owns the project
//   PROJECT_NUMBER      the project's number (the small integer in its URL)
//   PROJECT_FIELD_NAME  exact name of the Number field to set, e.g.
//                       "AI cost (USD)" -- must already exist on the project
//   CONTENT_NODE_IDS    comma-separated GraphQL node IDs of the issue(s)/PR(s)
//   COST_USD            the value to set
//
// Resolves the project + field once, then adds (idempotent) and updates the
// field for every node ID. Missing/invalid inputs are a warning, not a
// failure -- the comment step already carries the cost in plain text, so a
// misconfigured project (e.g. the field hasn't been created yet) shouldn't
// fail the run.
module.exports = async ({ github, context, core }) => {
  const owner = process.env.PROJECT_OWNER;
  const number = parseInt(process.env.PROJECT_NUMBER, 10);
  const fieldName = process.env.PROJECT_FIELD_NAME;
  const cost = parseFloat(process.env.COST_USD);
  const contentIds = (process.env.CONTENT_NODE_IDS || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  if (contentIds.length === 0) {
    core.info("No issue/PR node IDs to set the project field on; skipping.");
    return;
  }
  if (Number.isNaN(cost)) {
    core.warning("COST_USD is not a number; skipping project field update.");
    return;
  }

  const { user, organization } = await github.graphql(
    `query($login: String!, $number: Int!) {
      user(login: $login) {
        projectV2(number: $number) {
          id
          fields(first: 50) { nodes { ... on ProjectV2FieldCommon { id name } } }
        }
      }
      organization(login: $login) {
        projectV2(number: $number) {
          id
          fields(first: 50) { nodes { ... on ProjectV2FieldCommon { id name } } }
        }
      }
    }`,
    { login: owner, number }
  );
  const project = user?.projectV2 ?? organization?.projectV2;
  if (!project) {
    core.warning(`Project #${number} not found for owner "${owner}".`);
    return;
  }

  const field = project.fields.nodes.find((f) => f && f.name === fieldName);
  if (!field) {
    core.warning(
      `No field named "${fieldName}" on project #${number}. ` +
        "Add a Number field with this exact name to the project, then re-run."
    );
    return;
  }

  for (const contentId of contentIds) {
    const added = await github.graphql(
      `mutation($projectId: ID!, $contentId: ID!) {
        addProjectV2ItemById(input: { projectId: $projectId, contentId: $contentId }) {
          item { id }
        }
      }`,
      { projectId: project.id, contentId }
    );
    const itemId = added.addProjectV2ItemById.item.id;

    await github.graphql(
      `mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: Float!) {
        updateProjectV2ItemFieldValue(input: {
          projectId: $projectId, itemId: $itemId, fieldId: $fieldId, value: { number: $value }
        }) { projectV2Item { id } }
      }`,
      { projectId: project.id, itemId, fieldId: field.id, value: cost }
    );
    core.info(`Set "${fieldName}" = ${cost} on project item for ${contentId}`);
  }
};
