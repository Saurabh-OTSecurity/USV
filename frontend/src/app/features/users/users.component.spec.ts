import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';

import { UsersComponent } from './users.component';
import { API_BASE_URL } from '../../core/config';

describe('UsersComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [UsersComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('submits the create-user form to POST /api/v1/users', () => {
    const fixture = TestBed.createComponent(UsersComponent);
    const component = fixture.componentInstance;
    fixture.detectChanges();

    httpMock.expectOne(`${API_BASE_URL}/api/v1/users`).flush([]);

    component.form.setValue({
      username: 'new.user',
      password: 'SomeDevPassword1!',
      role: 'usv_viewer',
      display_name: 'New User',
      site_id: '',
    });
    component.submit();

    const createReq = httpMock.expectOne(`${API_BASE_URL}/api/v1/users`);
    expect(createReq.request.method).toBe('POST');
    expect(createReq.request.body).toEqual({
      username: 'new.user',
      password: 'SomeDevPassword1!',
      role: 'usv_viewer',
      display_name: 'New User',
      site_id: null,
    });

    createReq.flush({ user_id: 'u-2', username: 'new.user', role: 'usv_viewer', display_name: 'New User', site_id: null });

    httpMock.expectOne(`${API_BASE_URL}/api/v1/users`).flush([]);

    expect(component.successMessage()).toContain('new.user');
  });

  it('displays the backend validation error when an invalid role is submitted', () => {
    const fixture = TestBed.createComponent(UsersComponent);
    const component = fixture.componentInstance;
    fixture.detectChanges();

    httpMock.expectOne(`${API_BASE_URL}/api/v1/users`).flush([]);

    component.form.setValue({
      username: 'bad.role.user',
      password: 'SomeDevPassword1!',
      role: 'not_a_real_role',
      display_name: '',
      site_id: '',
    });
    component.submit();

    const createReq = httpMock.expectOne(`${API_BASE_URL}/api/v1/users`);
    createReq.flush(
      { error: { code: 'VALIDATION_ERROR', message: 'role must be one of the six valid values' } },
      { status: 422, statusText: 'Unprocessable Entity' }
    );

    expect(component.formError()).toBe('role must be one of the six valid values');
    expect(component.form.controls.password.value).toBe('');
  });
});
