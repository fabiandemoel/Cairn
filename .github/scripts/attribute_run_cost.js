// Shared github-script module: attribute one Claude Code run's cost to the
// issue(s)/PR(s) it touched. Each of the three Cairn agent workflows (scout,
// implement, replenish) resolves its own target number(s), then requires this
// module from an actions/github-script step and calls it.
//
// For every target it:
//   1. posts the run-cost markdown as a comment (REST, via the step's
//      github-token), and
//   2. idempotently adds the issue/PR to a Projects v2 board and sets a Number
//      field to the run's cost in USD (GraphQL, via projectsToken).
//
// The whole Projects v2 section is wrapped in try/catch: a missing board, a
// missing/renamed field, or a token without the `project` scope produces a
// core.warning, never a failed run. Comment posting is best-effort per target
// for the same reason. Scout may pass 0–3 targets; a multi-issue run sets the
// full run cost on each (accepted double-attribution).

module.exports = async ({
  github,
  context,
  core,
  targets,
  commentBody,
  costUsd,
  projectOwner,
  projectNumber,
  fieldName,
  projectsToken,
}) => {
  const nums = (targets || []).filter((n) => Number.isInteger(n) && n > 0);
  if (nums.length === 0) {
    core.info("attribute_run_cost: no issue/PR targets resolved; nothing to attribute.");
    return;
  }
  core.info(`attribute_run_cost: targets = ${nums.join(", ")}`);

  // 1. Comment on each target (PRs are issues for the comments API).
  if (commentBody && commentBody.trim()) {
    for (const issue_number of nums) {
      try {
        await github.rest.issues.createComment({
          owner: context.repo.owner,
          repo: context.repo.repo,
          issue_number,
          body: commentBody,
        });
        core.info(`Posted cost comment on #${issue_number}.`);
      } catch (err) {
        core.warning(`Could not comment on #${issue_number}: ${err.message}`);
      }
    }
  }

  // 2. Projects v2 Number field — entirely best-effort.
  const cost = Number(costUsd);
  if (!Number.isFinite(cost)) {
    core.info("attribute_run_cost: no numeric cost; skipping Projects v2 field update.");
    return;
  }

  try {
    const gql = (query, variables) =>
      github.graphql(query, {
        ...variables,
        headers: { authorization: `bearer ${projectsToken}` },
      });

    async function resolveProject(kind) {
      const query = `query($owner:String!, $number:Int!, $field:String!) {
        ${kind}(login: $owner) {
          projectV2(number: $number) {
            id
            title
            field(name: $field) {
              ... on ProjectV2FieldCommon { id name dataType }
            }
          }
        }
      }`;
      const data = await gql(query, {
        owner: projectOwner,
        number: projectNumber,
        field: fieldName,
      });
      return data[kind] ? data[kind].projectV2 : null;
    }

    let project = null;
    for (const kind of ["user", "organization"]) {
      try {
        project = await resolveProject(kind);
        if (project) break;
      } catch (err) {
        core.info(`Projects v2 lookup as ${kind} failed: ${err.message}`);
      }
    }

    if (!project) {
      core.warning(
        `Projects v2 board ${projectOwner}/#${projectNumber} not found (or token lacks ` +
          `the 'project' scope). Skipping field update.`,
      );
      return;
    }
    if (!project.field || !project.field.id) {
      core.warning(
        `Field "${fieldName}" not found on board "${project.title}". Skipping field update.`,
      );
      return;
    }
    if (project.field.dataType !== "NUMBER") {
      core.warning(
        `Field "${fieldName}" is ${project.field.dataType}, not NUMBER. Skipping field update.`,
      );
      return;
    }

    for (const number of nums) {
      try {
        const lookup = await gql(
          `query($owner:String!, $repo:String!, $number:Int!) {
            repository(owner: $owner, name: $repo) {
              issueOrPullRequest(number: $number) {
                __typename
                ... on Issue { id }
                ... on PullRequest { id }
              }
            }
          }`,
          { owner: context.repo.owner, repo: context.repo.repo, number },
        );
        const contentId = lookup.repository?.issueOrPullRequest?.id;
        if (!contentId) {
          core.warning(`Could not resolve node id for #${number}; skipping.`);
          continue;
        }

        const added = await gql(
          `mutation($project:ID!, $content:ID!) {
            addProjectV2ItemById(input: {projectId: $project, contentId: $content}) {
              item { id }
            }
          }`,
          { project: project.id, content: contentId },
        );
        const itemId = added.addProjectV2ItemById.item.id;

        await gql(
          `mutation($project:ID!, $item:ID!, $field:ID!, $value:Float!) {
            updateProjectV2ItemFieldValue(input: {
              projectId: $project, itemId: $item, fieldId: $field, value: {number: $value}
            }) { projectV2Item { id } }
          }`,
          { project: project.id, item: itemId, field: project.field.id, value: cost },
        );
        core.info(`Set "${fieldName}" = ${cost} on #${number} (item ${itemId}).`);
      } catch (err) {
        core.warning(`Could not set cost field on #${number}: ${err.message}`);
      }
    }
  } catch (err) {
    core.warning(`Projects v2 update skipped: ${err.message}`);
  }
};
