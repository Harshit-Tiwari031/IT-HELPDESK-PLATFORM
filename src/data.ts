export type Ticket = {
  id: string;
  title: string;
  category: string;
  priority: 'High' | 'Medium' | 'Low';
  status: 'Open' | 'In Progress' | 'Resolved';
  updated: string;
  updated_at?: string;
  created_at?: string;
  resolution?: string | null;
  description: string;
  owner: string;
};

export const articles = [
  { title: 'Troubleshoot a dropped VPN connection', category: 'Network', time: '4 min read', intro: 'Restore a stable remote connection with a few quick checks.', steps: ['Confirm your internet connection is stable without the VPN.', 'Disconnect and reconnect to the nearest approved gateway.', 'Restart the VPN client and check for pending updates.', 'If disconnects continue, note the time and your network type before contacting IT.'] },
  { title: 'Connect to campus Wi-Fi', category: 'Network', time: '3 min read', intro: 'Set up your device on the secure campus network.', steps: ["Select the college's verified secure Wi-Fi network; confirm its exact name with official campus IT if you are unsure.", 'Sign in with your college account. Verify any certificate details against official campus IT instructions, and do not accept an unexpected or unverified certificate warning.', 'Forget older saved campus networks if authentication fails.', 'If a certificate warning remains unclear, stop and contact campus IT using independently verified contact information before connecting.', 'Restart Wi-Fi and try again near an access point after the network and certificate are verified.'] },
  { title: 'Request access to a shared drive', category: 'Access', time: '2 min read', intro: 'Get the right permissions for shared team files.', steps: ['Connect to the campus network or approved VPN.', 'Confirm you are signed in with your college account.', 'Ask the folder owner to confirm your group membership.', 'Create a ticket with the drive path if access is still denied.'] },
  { title: 'Improve a slow computer', category: 'Hardware', time: '5 min read', intro: 'Try these safe steps before requesting device support.', steps: ['Restart your computer to finish pending updates.', 'Close apps and browser tabs you are not using.', 'Check available storage and remove unneeded downloads.', 'Record the apps affected if slowness continues.'] },
  { title: 'Set up your authenticator on a new phone', category: 'Account', time: '3 min read', intro: 'Regain secure access after changing devices.', steps: ['Keep your previous device available if you still have it.', 'Open the account security page on a trusted browser.', 'Choose Add sign-in method and follow the authenticator prompts.', 'Contact IT for identity verification if you are locked out.'] },
  { title: 'Refresh desktop email sync', category: 'Software', time: '2 min read', intro: 'Check common causes of delayed email updates.', steps: ['Confirm the desktop client is online.', 'Use Sync or Refresh to request new messages.', 'Restart the mail client and check for updates.', 'Use webmail temporarily if the delay continues.'] },
];

export const workflowSteps = [
  { name: 'Issue received', status: 'complete', detail: 'Ticket HD-2481 received · VPN disconnects during calls', evidence: 'Requester description and category: Network' },
  { name: 'AI diagnosis', status: 'complete', detail: 'Possible unstable gateway connection identified', evidence: 'DEMO · Classification confidence 94%' },
  { name: 'Knowledge base lookup', status: 'complete', detail: 'Matched “Troubleshoot a dropped VPN connection”', evidence: 'DEMO · 3 relevant steps found' },
  { name: 'Diagnostic tool executed', status: 'complete', detail: 'Connectivity check prepared for review', evidence: 'SIMULATED · No device was accessed or checked' },
  { name: 'Verification', status: 'active', detail: 'Waiting for requester to confirm connection stability', evidence: 'DEMO · User confirmation required' },
  { name: 'Resolved or escalated', status: 'pending', detail: 'Escalation to Network Support if issue persists', evidence: 'DEMO · No remediation has been executed' },
];
