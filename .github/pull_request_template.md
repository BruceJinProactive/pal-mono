## Checklist

### Before merging
- [ ] Test: I have tested my changes locally and verified the changes work as expected. [api](http://localhost:8000/docs), [app](http://localhost:8501/)
### After merging
- [ ] Deploy: I have verified the deployment was successful. Deployment status is updated in [#devops-release-lat-pal-mono](https://proactiveailabgroup.slack.com/archives/C07H6H6MVV0).
- [ ] Test: I have verified that the changes work as expected on `lat` environment. [api](http://pal-mono-lat-api-lb-1443082111.us-west-1.elb.amazonaws.com/docs), [app](http://pal-mono-lat-app-lb-1258791823.us-west-1.elb.amazonaws.com/)
- [ ] Monitor: I have monitored the `lat` environment stay healthy for 10 minutes after deployment. Health status is updated in [#devops-health-lat](https://proactiveailabgroup.slack.com/archives/C07KAU9AUBC). 