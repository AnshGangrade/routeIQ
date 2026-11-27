import { api } from './api';
import { validateRouteResult, watchTask, activeStatus } from './product';
import { completedMeasurement } from './routeEvidence';
import type { InstanceResponse, RoutingResultResponse, MethodComparison } from '../types/api';

export const comparisonMethods = ['nearest_neighbor', '2opt', 'portfolio'] as const;
export const comparisonBudget = { operations:100000, seconds:10, search_seed:0 };
export interface ComparisonProgress { status:string; stage:string; errors:string[]; }
export function recommendedResult(rows:MethodComparison[], instance?:InstanceResponse) {
  const completed=instance ? rows.filter(r=>completedMeasurement(instance,r)) : [];
  return completed.reduce<MethodComparison|null>((best,r)=>!best||r.total_distance<best.total_distance?r:best,null);
}
/** One scoped run, using the existing endpoints and their independent validators. */
export class ComparisonRun {
  cancelled=false;
  private started=false;
  jobId:string|null=null;
  constructor(private instance:InstanceResponse, private progress:(p:ComparisonProgress)=>void,
    private result:(r:RoutingResultResponse)=>void, private client=api) {}
  async cancel() {
    this.cancelled=true;
    this.progress({status:'cancelling',stage:'Stopping comparison. An in-flight baseline request must finish; no further methods will start.',errors:[]});
    if(this.jobId) {
      const response=await this.client.cancelOptimization(this.jobId);
      if(response.job_id!==this.jobId || response.instance_id!==this.instance.instance_id) throw new Error('Unexpected cancellation identity.');
    }
  }
  async run() {
    if(this.started)return;this.started=true;
    const errors:string[]=[];let incomplete=false;let successful=0;
    for(const method of comparisonMethods) {
      if(this.cancelled) break;
      this.progress({status:'running',stage:method==='portfolio'?'Finding a better plan':method==='2opt'?'Refining the starting routes':'Calculating starting routes',errors:[...errors]});
      try {
        let row:RoutingResultResponse;
        if(method==='portfolio') {
          const job=await this.client.startOptimization({instance_id:this.instance.instance_id,method,...comparisonBudget});
          if(job.instance_id!==this.instance.instance_id || job.method!==method) throw new Error('Unexpected comparison job identity.');
          this.jobId=job.job_id;
          if(this.cancelled) await this.cancel();
          row=await new Promise((resolve,reject)=>{
            let stop=()=>{};
            stop=watchTask(job.job_id,this.client.optimizationStatus,(value)=>{
              if(value.instance_id!==this.instance.instance_id || value.method!==method || value.matrix_fingerprint!==this.instance.matrix_fingerprint || value.problem_fingerprint!==this.instance.problem_fingerprint) {stop();reject(new Error('Comparison job belongs to another problem.'));return;}
              if(!activeStatus(value.status)) {stop();if(value.result && ['completed','incomplete'].includes(value.status)) resolve(value.result);else reject(new Error(value.error||`Improved method ${value.status}`));}
            },(message,terminal)=>{this.progress({status:this.cancelled?'cancelling':'running',stage:`Progress unavailable: ${message}. ${terminal?'Retry comparison.':'Retrying automatically.'}`,errors:[...errors]});if(terminal){stop();reject(new Error(message));}});
          });
          this.jobId=null;
        } else row=await this.client.solveRouting({instance_id:this.instance.instance_id,method});
        validateRouteResult(this.instance,row);
        if(row.method!==method || row.execution?.status==='failed') throw new Error('Invalid comparison method or failed evaluation.');
        if(row.execution?.status==='incomplete') incomplete=true;
        else if(!completedMeasurement(this.instance,row)) throw new Error('Comparison did not return completed, verified measurements.');
        else if(!this.cancelled) {this.result(row);successful++;}
      } catch(e) { errors.push(`${method}: ${e instanceof Error?e.message:'Calculation failed'}`); }
    }
    this.progress({status:this.cancelled?'cancelled':!successful?'failed':errors.length||incomplete?'incomplete':'completed',stage:this.cancelled?'Comparison cancelled; prior routes retained.':errors.length?'Some methods failed. Retry comparison or inspect diagnostics.':incomplete?'Comparison returned valid routes; improved search stopped early.':'Comparison complete.',errors});
  }
}
