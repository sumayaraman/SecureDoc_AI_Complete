'use client';
import { Shell } from '../../components/shell';
import { Card, Button } from '../../components/ui';
import { User, Building2, Bell, Shield } from 'lucide-react';

const items = [
  [User, 'Profile', 'Manage your personal information'],
  [Building2, 'Organization', 'Update company details'],
  [Bell, 'Notifications', 'Configure alert preferences'],
  [Shield, 'Security', 'Password and 2FA settings'],
];

export default function Settings() {
  return (
    <Shell>
      <div>
        <p className="text-sm font-medium text-indigo-600">Configuration</p>
        <h1 className="mt-1 text-2xl font-bold">Settings</h1>
      </div>
      <div className="mt-6 grid gap-4">
        {items.map(([Icon, title, desc]: any) => (
          <Card key={title} className="flex items-center gap-4 p-5">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-indigo-50 text-indigo-600">
              <Icon size={20} />
            </div>
            <div className="flex-1">
              <p className="font-medium">{title}</p>
              <p className="text-sm text-slate-500">{desc}</p>
            </div>
            <Button variant="outline" size="sm">Manage</Button>
          </Card>
        ))}
      </div>
    </Shell>
  );
}