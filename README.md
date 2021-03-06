Nagbot [![Build Status](https://img.shields.io/circleci/build/github/srosenthal/nagbot)](https://circleci.com/gh/srosenthal/nagbot) [![License](https://img.shields.io/github/license/srosenthal/nagbot)](https://github.com/srosenthal/nagbot/blob/master/LICENSE)
=========

# The Problem
Amazon Web Services provides incredible flexibility for quickly spinning up servers with a variety of configurations. The big downside is that it's easy to lose track of AWS resources and end up spending a lot more money than you expected.

At Seeq, we launch a lot of EC2 instances for a variety of development purposes (demos, testing, research & development). But we aren't always good about keeping track of them. Before Nagbot came along, cleaning up unwanted or forgotten EC2 instances was a manual process. I saw an opportunity there and volunteered to implement an automated process.


# Nagbot
Nagbot is a side project I developed at [Seeq](https://seeq.com) and launched in May 2019. It has saved thousands of dollars every month, probably tens of thousands in the few months it has been running so far.

Nagbot does the following:
1. Query for all of the running EC2 instances in an account, along with important metadata (Name, OS, Monthly Price, etc.)
2. Post this information to a Slack channel and also dump the table into a Google Sheet for analysis and auditing
3. Look at the "Stop after" tag, which is by convention a YYYY-MM-DD date, and after a warning period, stop any unwanted instances.

Here's what a Nagbot notification looks like in Slack:
![Example of Nagbot's Slack message](https://github.com/srosenthal/nagbot/blob/master/nagbot-slack.png "Example of Nagbot's Slack message")
