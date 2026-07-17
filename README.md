Nagbot [![Build Status](https://img.shields.io/circleci/build/github/srosenthal/nagbot)](https://circleci.com/gh/srosenthal/nagbot) [![License](https://img.shields.io/github/license/srosenthal/nagbot)](https://github.com/srosenthal/nagbot/blob/master/LICENSE)
=========

# The Problem
Amazon Web Services provides incredible flexibility for quickly spinning up servers with a variety of configurations. The big downside is that it's easy to lose track of AWS resources and end up spending a lot more money than you expected.

At Seeq, we launch a lot of EC2 instances for a variety of development purposes (demos, testing, research & development). But we aren't always good about keeping track of them. Before Nagbot came along, cleaning up unwanted or forgotten EC2 instances was a manual process. I saw an opportunity there and volunteered to implement an automated process.


# Nagbot
Nagbot is a side project I developed at [Seeq](https://seeq.com) and launched in May 2019. It has saved thousands of dollars every month, probably tens of thousands in the few months it has been running so far.

Nagbot does the following:
1. Query for all EC2 Instances, Volumes, AMIs, and Snapshots in an account, along 
   with important metadata (Name, OS, Monthly Price, size, etc.)
2. Post this information to a Slack channel and also dump the table into an Excel spreadsheet in an S3 bucket for 
   analysis and auditing
3. Look at the "Stop after" tag, which is by convention a YYYY-MM-DD date, and after a warning period, stop any 
   unwanted resources.
4. Look at the "Terminate after" tag, which is by convention a YYYY-MM-DD date, and terminate any unwanted resources.

Here's what a Nagbot notification looks like in Slack:
![Example of Nagbot's Slack message](https://github.com/srosenthal/nagbot/blob/master/nagbot-slack.png "Example of Nagbot's Slack message")

# Setting up Slack for Nagbot

Here is a [recording of the process to setup a Slack app](https://seeq.zoom.us/rec/share/qgmqAvz_2eV3SYiNJO4mLrQlH94eGXSs89BDSl28Epl-Bjey9_DgvBLnkF3W2dOf.Zd12Sq-G5QbsOPrt) (Passcode: z?mJ%d08). The process frequently changes due to Slack changing the UI for applications.

# Testing Nagbot changes during development

The NagBotTest app has been registered to slack, and it is set up to send NagBot output to slack. The default 
testing channel for NagBot is #bot-testing. 

For Seeq employees looking to test changes to NagBot during development, the SLACK_BOT_TOKEN for NagBotTest is found on 
Keeper [here]
(https://keepersecurity.
com/vault/#detail/AUj3FYXz44uON4CVQSTKMQ).

# Deploying (Seeq Employees)

**A merge to `master` is a deploy.** GitHub Actions builds the image and Flux rolls it out to the production Nagbot job on the `use1-i` cluster automatically — there is no separate devops PR or manual `kubectl apply`. Treat every merge as shipping to production; the next scheduled Nagbot run will use the new image.

Do not merge a PR until it is ready to run in production. That includes any dependent changes outside this repo (for example changes in the devops repo, or AWS/Slack configuration) that the Nagbot change needs. If those are not ready, keep the PR open (or draft) until they are.

After a PR merges to `master`, GitHub Actions builds and pushes the Nagbot image to Docker Hub with two tags:

- `<sha_short>` — short git SHA (e.g. `c9f970a`)
- `<UTC-timestamp>-<sha_short>` — Flux-compatible tag (e.g. `20260716180852-c9f970a`)

Flux Image Automation on the `use1-i` cluster watches `docker.io/seeqsaas/nagbot`, selects the newest timestamp tag, and commits it to `sk8park/development/aws-internal/use1-i/nagbot/image-tag.yaml` on the devops `develop` branch. That commit triggers the existing Terragrunt apply workflow, which rolls out the new image. No manual devops tag-bump PR is required.

For rollback and more detail, see [Flux Image Automation (use1-i tooling cluster)](https://seeq.atlassian.net/wiki/spaces/SQ/pages/5307432970).
